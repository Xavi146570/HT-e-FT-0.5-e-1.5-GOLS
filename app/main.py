from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
import os
import asyncio
# Adicione para keep-alive no Render:
import httpx
from datetime import datetime

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
from app.config import MIN_EDGE_ALERT, LIVE_SCAN_KEY, RENDER_URL

app = FastAPI(title="Liga Portugal Live Scanner Protegido", version="2.2.0")

class PredictionRequest(BaseModel):
    home_team: str
    away_team: str
    season_for_odds: Optional[int] = 2024
    send_alert: bool = True

def odds_to_probability(odd: float) -> float:
    if odd <= 1.0: 
        return 0.0
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
    except Exception as e: 
        print(f"Erro ao extrair odds: {e}")
    return extracted

@app.get("/")
def root():
    return {
        "status": "ok", 
        "message": "Scanner Protegido Ativo",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/health")
async def health_check():
    """Endpoint para keep-alive no Render (a cada 14 minutos)"""
    return {"status": "alive", "time": datetime.now().isoformat()}

@app.get("/live-scan")
async def live_scan(key: str = Query(None)):
    """
    Endpoint protegido para varrer jogos AO VIVO.
    Exige ?key=SUA_CHAVE no URL.
    """
    if key != LIVE_SCAN_KEY:
        raise HTTPException(status_code=403, detail="Acesso negado: Chave de segurança inválida.")

    try:
        live_fixtures = await get_live_fixtures_liga_portugal()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar jogos: {str(e)}")

    if not live_fixtures:
        return {"message": "Nenhum jogo da Liga Portugal a decorrer agora.", "alerts": []}

    results = []
    errors = []
    
    for fx in live_fixtures:
        try:
            f_id = fx["fixture"]["id"]
            home_name = fx["teams"]["home"]["name"]
            away_name = fx["teams"]["away"]["name"]
            elapsed = fx["fixture"]["status"]["elapsed"] or 0
            goals_home = fx["goals"]["home"] or 0
            goals_away = fx["goals"]["away"] or 0
            total_goals = goals_home + goals_away

            # Buscar histórico e calcular P-Min
            h_id = fx["teams"]["home"]["id"]
            a_id = fx["teams"]["away"]["id"]
            
            # Parallel fetching para performance
            h_fix, a_fix = await asyncio.gather(
                get_league_fixtures_for_team(h_id),
                get_league_fixtures_for_team(a_id)
            )
            
            stats_h = compute_over_stats_from_fixtures(h_fix)
            stats_a = compute_over_stats_from_fixtures(a_fix)
            probs = compute_game_probs(stats_h, stats_a)

            # Buscar Odds Live
            odds_raw = await get_odds_for_live_fixture(f_id)
            live_odds = extract_odds_from_response(odds_raw)

            # Lógica Over 0.5 HT (0-0 entre 15' e 35')
            if total_goals == 0 and 15 <= elapsed <= 35:
                market = "over05_ht"
                odd = live_odds.get(market)
                if odd:
                    p_mkt = odds_to_probability(odd)
                    p_min = probs.get(market, {}).get("p_min", 0)
                    edge = p_min - p_mkt
                    
                    if edge >= MIN_EDGE_ALERT:
                        msg = format_alert_message(
                            home_name, away_name, "LIVE Over 0.5 HT", 
                            p_min, p_mkt, edge, odd
                        )
                        msg += f"\n⏱ Tempo: {elapsed}' | Placar: 0-0"
                        
                        try:
                            await send_telegram_message(msg)
                            results.append({
                                "type": "HT", 
                                "match": f"{home_name} vs {away_name}",
                                "edge": round(edge, 3),
                                "odd": odd
                            })
                        except Exception as e:
                            errors.append(f"Telegram HT {home_name}: {str(e)}")

            # Lógica Over 1.5 FT (Até 1 golo até aos 65')
            if total_goals <= 1 and elapsed <= 65:
                market = "over15_ft"
                odd = live_odds.get(market)
                if odd:
                    p_mkt = odds_to_probability(odd)
                    p_min = probs.get(market, {}).get("p_min", 0)
                    edge = p_min - p_mkt
                    
                    if edge >= MIN_EDGE_ALERT:
                        msg = format_alert_message(
                            home_name, away_name, "LIVE Over 1.5 FT", 
                            p_min, p_mkt, edge, odd
                        )
                        msg += f"\n⏱ Tempo: {elapsed}' | Placar: {goals_home}-{goals_away}"
                        
                        try:
                            await send_telegram_message(msg)
                            results.append({
                                "type": "FT", 
                                "match": f"{home_name} vs {away_name}",
                                "edge": round(edge, 3),
                                "odd": odd
                            })
                        except Exception as e:
                            errors.append(f"Telegram FT {home_name}: {str(e)}")

        except Exception as e:
            errors.append(f"Erro no jogo {fx.get('fixture', {}).get('id', 'unknown')}: {str(e)}")
            continue

    return {
        "processed": len(live_fixtures), 
        "alerts_sent": len(results),
        "alerts": results,
        "errors": errors if errors else None
    }

@app.post("/predict")
async def predict(req: PredictionRequest):
    """Predict manual para testes"""
    try:
        home_id, away_id = await asyncio.gather(
            get_team_id_by_name(req.home_team),
            get_team_id_by_name(req.away_team)
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    home_fixtures, away_fixtures = await asyncio.gather(
        get_league_fixtures_for_team(home_id),
        get_league_fixtures_for_team(away_id)
    )
    
    home_stats = compute_over_stats_from_fixtures(home_fixtures)
    away_stats = compute_over_stats_from_fixtures(away_fixtures)
    probs = compute_game_probs(home_stats, away_stats)

    return {
        "home": req.home_team, 
        "away": req.away_team, 
        "probabilities": probs,
        "timestamp": datetime.now().isoformat()
    }

# Keep-alive para Render (executa a cada 14 minutos)
@app.on_event("startup")
async def startup_event():
    """Inicia o keep-alive para evitar que o Render durma"""
    if os.getenv("RENDER"):
        asyncio.create_task(keep_alive_task())

async def keep_alive_task():
    """Ping a si próprio a cada 14 minutos"""
    url = RENDER_URL or "http://localhost:8000/health"
    while True:
        await asyncio.sleep(14 * 60)  # 14 minutos
        try:
            async with httpx.AsyncClient() as client:
                await client.get(url, timeout=10)
                print(f"Keep-alive ping enviado: {datetime.now()}")
        except Exception as e:
            print(f"Erro no keep-alive: {e}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
