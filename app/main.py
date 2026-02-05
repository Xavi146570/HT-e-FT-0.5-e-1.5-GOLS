from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
from app.data_fetcher import (
    get_team_id_by_name,
    get_league_fixtures_for_team,
    compute_over_stats_from_fixtures,
    get_odds_for_fixture,
    get_live_fixtures_liga_portugal,
    get_odds_for_live_fixture
)
from app.model import compute_game_probs
from app.telegram_notifier import send_telegram_message, format_alert_message
from app.config import MIN_EDGE_ALERT

app = FastAPI(title="Liga Portugal Live Scanner", version="2.0.0")

class PredictionRequest(BaseModel):
    home_team: str
    away_team: str
    season_for_odds: int | None = 2024
    send_alert: bool = True

def odds_to_probability(odd: float) -> float:
    if odd <= 1.0: return 0.0
    return 1.0 / odd

def extract_odds_from_response(odds_data: dict) -> dict:
    extracted = {"over05_ht": None, "over15_ft": None}
    try:
        bookmakers = odds_data.get("response", [{}])[0].get("bookmakers", [])
        for bm in bookmakers:
            for bet in bm.get("bets", []):
                if bet["name"] == "Goals Over/Under":
                    for val in bet["values"]:
                        if val["value"] == "Over 1.5":
                            extracted["over15_ft"] = float(val["odd"])
                if bet["name"] == "Goals Over/Under First Half":
                    for val in bet["values"]:
                        if val["value"] == "Over 0.5":
                            extracted["over05_ht"] = float(val["odd"])
    except Exception: pass
    return extracted

@app.get("/")
def root():
    return {"status": "ok", "message": "Scanner Live Liga Portugal Ativo"}

@app.get("/live-scan")
async def live_scan():
    """
    Endpoint para varrer jogos AO VIVO e enviar alertas automáticos.
    """
    live_fixtures = await get_live_fixtures_liga_portugal()
    if not live_fixtures:
        return {"message": "Nenhum jogo da Liga Portugal a decorrer agora."}

    results = []
    for fx in live_fixtures:
        f_id = fx["fixture"]["id"]
        home_name = fx["teams"]["home"]["name"]
        away_name = fx["teams"]["away"]["name"]
        elapsed = fx["fixture"]["status"]["elapsed"]
        goals_home = fx["goals"]["home"]
        goals_away = fx["goals"]["away"]
        total_goals = goals_home + goals_away

        # 1. Buscar histórico para calcular P-Min
        h_id = fx["teams"]["home"]["id"]
        a_id = fx["teams"]["away"]["id"]
        h_fix = await get_league_fixtures_for_team(h_id)
        a_fix = await get_league_fixtures_for_team(a_id)
        
        stats_h = compute_over_stats_from_fixtures(h_fix)
        stats_a = compute_over_stats_from_fixtures(a_fix)
        probs = compute_game_probs(stats_h, stats_a)

        # 2. Buscar Odds Live
        odds_raw = await get_odds_for_live_fixture(f_id)
        live_odds = extract_odds_from_response(odds_raw)

        # 3. Lógica de Alerta Live
        # Exemplo: Se o jogo está 0-0 e estamos entre os 15' e 35' minutos
        if total_goals == 0 and 15 <= elapsed <= 35:
            market = "over05_ht"
            odd = live_odds.get(market)
            if odd:
                p_mkt = odds_to_probability(odd)
                edge = probs[market]["p_min"] - p_mkt
                if edge >= MIN_EDGE_ALERT:
                    msg = format_alert_message(home_name, away_name, "LIVE Over 0.5 HT", probs[market]["p_min"], p_mkt, edge, odd)
                    msg += f"\n⏱ Tempo: {elapsed}' | Placar: 0-0"
                    await send_telegram_message(msg)
                    results.append(f"Alerta enviado: {home_name} vs {away_name}")

        # Exemplo: Over 1.5 FT se o jogo ainda tem 0 ou 1 golo até aos 60'
        if total_goals <= 1 and elapsed <= 65:
            market = "over15_ft"
            odd = live_odds.get(market)
            if odd:
                p_mkt = odds_to_probability(odd)
                edge = probs[market]["p_min"] - p_mkt
                if edge >= MIN_EDGE_ALERT:
                    msg = format_alert_message(home_name, away_name, "LIVE Over 1.5 FT", probs[market]["p_min"], p_mkt, edge, odd)
                    msg += f"\n⏱ Tempo: {elapsed}' | Placar: {goals_home}-{goals_away}"
                    await send_telegram_message(msg)
                    results.append(f"Alerta enviado FT: {home_name} vs {away_name}")

    return {"processed_fixtures": len(live_fixtures), "alerts": results}

@app.post("/predict")
async def predict(req: PredictionRequest):
    # Mantém o endpoint predict original para consultas manuais
    try:
        home_id = await get_team_id_by_name(req.home_team)
        away_id = await get_team_id_by_name(req.away_team)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    home_fixtures = await get_league_fixtures_for_team(home_id)
    away_fixtures = await get_league_fixtures_for_team(away_id)
    home_stats = compute_over_stats_from_fixtures(home_fixtures)
    away_stats = compute_over_stats_from_fixtures(away_fixtures)
    probs = compute_game_probs(home_stats, away_stats)

    odds_raw = {}
    real_odds = {"over05_ht": None, "over15_ft": None}
    if req.season_for_odds:
        try:
            odds_raw = await get_odds_for_fixture(home_id, away_id, req.season_for_odds)
            real_odds = extract_odds_from_response(odds_raw)
        except Exception: pass

    return {
        "home_team": req.home_team,
        "away_team": req.away_team,
        "probabilities": probs,
        "odds_found": real_odds
    }
