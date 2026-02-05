from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from .data_fetcher import (
    get_team_id_by_name,
    get_league_fixtures_for_team,
    compute_over_stats_from_fixtures,
    get_odds_for_fixture,
)
from .model import compute_game_probs

app = FastAPI(title="Liga Portugal Over Goals Model")

class PredictionRequest(BaseModel):
    home_team: str
    away_team: str
    season_for_odds: int | None = None  # p.ex. 2024

@app.get("/")
def root():
    return {"status": "ok", "message": "Liga Portugal Over Goals API"}

@app.post("/predict")
async def predict(req: PredictionRequest):
    try:
        home_id = await get_team_id_by_name(req.home_team)
        away_id = await get_team_id_by_name(req.away_team)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    # histórico das equipas (2020–2024)
    home_fixtures = await get_league_fixtures_for_team(home_id)
    away_fixtures = await get_league_fixtures_for_team(away_id)

    if not home_fixtures or not away_fixtures:
        raise HTTPException(status_code=400, detail="No historic fixtures found for one or both teams.")

    home_stats = compute_over_stats_from_fixtures(home_fixtures)
    away_stats = compute_over_stats_from_fixtures(away_fixtures)

    probs = compute_game_probs(home_stats, away_stats)

    # odds – opcional (pode falhar por não haver fixture ou odds recentes)
    odds_info = {}
    if req.season_for_odds:
        try:
            odds_info = await get_odds_for_fixture(home_id, away_id, req.season_for_odds)
        except Exception:
            odds_info = {"warning": "Failed to fetch odds or fixture."}

    return {
        "home_team": req.home_team,
        "away_team": req.away_team,
        "probs": probs,
        "raw_stats": {
            "home": home_stats,
            "away": away_stats,
        },
        "odds_raw": odds_info,
    }
