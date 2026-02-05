from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from app.data_fetcher import (
    get_team_id_by_name,
    get_league_fixtures_for_team,
    compute_over_stats_from_fixtures,
    get_odds_for_fixture,
)
from app.model import compute_game_probs
from app.telegram_notifier import send_telegram_message, format_alert_message
from app.config import MIN_EDGE_ALERT

app = FastAPI(title="Liga Portugal Over Goals Model", version="1.1.0")

class PredictionRequest(BaseModel):
    home_team: str
    away_team: str
    season_for_odds: int | None = 2024
    send_alert: bool = True

def odds_to_probability(odd: float) -> float:
    """Converte odd decimal em probabilidade implícita."""
    if odd <= 1.0:
        return 0.0
    return 1.0 / odd

def extract_odds_from_response(odds_data: dict) -> dict:
    """
    Tenta extrair as odds de Over 0.5 HT e Over 1.5 FT da resposta da API.
    Nota: A estrutura da API de Odds é complexa, este é um extrator simplificado.
    """
    extracted = {"over05_ht": None, "over15_ft": None}
    
    try:
        # Navega pela estrutura da API-Football (Bookmaker 8 = Bet365 habitualmente)
        bookmakers = odds_data.get("response", [{}])[0].get("bookmakers", [])
        for bm in bookmakers:
            for bet in bm.get("bets", []):
                # Over/Under Full Time
                if bet["name"] == "Goals Over/Under":
                    for val in bet["values"]:
                        if val["value"] == "Over 1.5":
                            extracted["over15_ft"] = float(val["odd"])
                
                # Over/Under First Half
                if bet["name"] == "Goals Over/Under First Half":
                    for val in bet["values"]:
                        if val["value"] == "Over 0.5":
                            extracted["over05_ht"] = float(val["odd"])
    except Exception:
        pass
    return extracted

@app.get("/")
def root():
    return {"status": "ok", "message": "Liga Portugal Over Goals API com Telegram"}

@app.post("/predict")
async def predict(req: PredictionRequest):
    try:
        home_id = await get_team_id_by_name(req.home_team)
        away_id = await get_team_id_by_name(req.away_team)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # 1. Buscar histórico
    home_fixtures = await get_league_fixtures_for_team(home_id)
    away_fixtures = await get_league_fixtures_for_team(away_id)

    if not home_fixtures or not away_fixtures:
        raise HTTPException(status_code=400, detail="Histórico insuficiente para estas equipas.")

    # 2. Calcular estatísticas e probabilidades
    home_stats = compute_over_stats_from_fixtures(home_fixtures)
    away_stats = compute_over_stats_from_fixtures(away_fixtures)
    probs = compute_game_probs(home_stats, away_stats)

    # 3. Buscar Odds reais
    odds_raw = {}
    real_odds = {"over05_ht": None, "over15_ft": None}
    
    if req.season_for_odds:
        try:
            odds_raw = await get_odds_for_fixture(home_id, away_id, req.season_for_odds)
            real_odds = extract_odds_from_response(odds_raw)
        except Exception:
            pass

    # 4. Verificar Valor e Enviar Alertas
    alerts_sent = []
    if req.send_alert:
        for market_key, odd in real_odds.items():
            if odd:
                p_market = odds_to_probability(odd)
                p_min = probs[market_key]["p_min"]
                edge = p_min - p_market
                
                if edge >= MIN_EDGE_ALERT:
                    market_name = "Over 0.5 HT" if market_key == "over05_ht" else "Over 1.5 FT"
                    msg = format_alert_message(
                        home_team=req.home_team,
                        away_team=req.away_team,
                        market=market_name,
                        p_min=p_min,
                        p_market=p_market,
                        edge=edge,
                        odd=odd,
                    )
                    success = await send_telegram_message(msg)
                    alerts_sent.append({"market": market_name, "sent": success, "edge": round(edge, 4)})

    return {
        "home_team": req.home_team,
        "away_team": req.away_team,
        "probabilities": probs,
        "odds_found": real_odds,
        "alerts": alerts_sent,
        "debug_stats": {"home": home_stats, "away": away_stats}
    }
