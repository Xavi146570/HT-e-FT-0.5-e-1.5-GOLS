import httpx
from typing import List, Dict
from app.config import (
    API_FOOTBALL_KEY,
    API_FOOTBALL_BASE_URL,
    LIGA_PORTUGAL_ID,
    HISTORIC_SEASONS,
)

HEADERS = {
    "x-apisports-key": API_FOOTBALL_KEY,
}


async def get_team_id_by_name(team_name: str) -> int:
    async with httpx.AsyncClient(
        base_url=API_FOOTBALL_BASE_URL, headers=HEADERS, timeout=20
    ) as client:
        r = await client.get("/teams", params={"search": team_name})
        r.raise_for_status()
        data = r.json()
        for item in data.get("response", []):
            if item["team"]["name"].lower() == team_name.lower():
                return item["team"]["id"]
    raise ValueError(f"Team not found: {team_name}")


async def get_league_fixtures_for_team(team_id: int) -> List[Dict]:
    fixtures: List[Dict] = []
    async with httpx.AsyncClient(
        base_url=API_FOOTBALL_BASE_URL, headers=HEADERS, timeout=20
    ) as client:
        for season in HISTORIC_SEASONS:
            page = 1
            while True:
                r = await client.get(
                    "/fixtures",
                    params={
                        "team": team_id,
                        "league": LIGA_PORTUGAL_ID,
                        "season": season,
                        "page": page,
                    },
                )
                r.raise_for_status()
                data = r.json()
                fixtures.extend(data.get("response", []))

                paging = data.get("paging", {})
                if page >= paging.get("total", 1):
                    break
                page += 1
    return fixtures


def compute_over_stats_from_fixtures(fixtures: List[Dict]) -> Dict[str, float]:
    """
    A partir da lista de fixtures históricos, calcula:
    - over_05_ht_s, over_05_ht_n
    - over_15_ft_s, over_15_ft_n
    """
    over_05_ht_s = 0
    over_05_ht_n = 0
    over_15_ft_s = 0
    over_15_ft_n = 0

    for fx in fixtures:
        if fx.get("fixture", {}).get("status", {}).get("short") != "FT":
            continue

        goals = fx.get("goals", {})
        score = fx.get("score", {})

        # Half-time
        ht = score.get("halftime", {})
        ht_home = ht.get("home")
        ht_away = ht.get("away")

        if ht_home is not None and ht_away is not None:
            total_ht = ht_home + ht_away
            over_05_ht_n += 1
            if total_ht >= 1:
                over_05_ht_s += 1

        # Full-time
        ft_home = goals.get("home")
        ft_away = goals.get("away")
        if ft_home is not None and ft_away is not None:
            total_ft = ft_home + ft_away
            over_15_ft_n += 1
            if total_ft >= 2:
                over_15_ft_s += 1

    return {
        "over_05_ht_s": over_05_ht_s,
        "over_05_ht_n": over_05_ht_n,
        "over_15_ft_s": over_15_ft_s,
        "over_15_ft_n": over_15_ft_n,
    }


async def get_odds_for_fixture(home_id: int, away_id: int, season: int) -> Dict:
    """
    Busca odds para um fixture histórico (head-to-head) – mantém para uso pré-live.
    """
    async with httpx.AsyncClient(
        base_url=API_FOOTBALL_BASE_URL, headers=HEADERS, timeout=20
    ) as client:
        r = await client.get(
            "/fixtures/headtohead",
            params={
                "h2h": f"{home_id}-{away_id}",
                "league": LIGA_PORTUGAL_ID,
                "season": season,
            },
        )
        r.raise_for_status()
        data = r.json()
        fixtures = data.get("response", [])
        if not fixtures:
            return {}

        fixture = fixtures[-1]
        fixture_id = fixture["fixture"]["id"]

        r2 = await client.get("/odds", params={"fixture": fixture_id, "bookmaker": 8})
        r2.raise_for_status()
        odds_data = r2.json()
        return odds_data


# =========================
#   LIVE FIXTURES (AO VIVO)
# =========================

async def get_live_fixtures_liga_portugal() -> List[Dict]:
    """
    Vai buscar todos os jogos AO VIVO da Liga Portugal.
    Usa o endpoint /fixtures?live=all e filtra pela liga.
    """
    async with httpx.AsyncClient(
        base_url=API_FOOTBALL_BASE_URL, headers=HEADERS, timeout=20
    ) as client:
        r = await client.get("/fixtures", params={"live": "all"})
        r.raise_for_status()
        data = r.json()
        all_live = data.get("response", [])

        liga_live = [
            fx for fx in all_live
            if fx.get("league", {}).get("id") == LIGA_PORTUGAL_ID
        ]
        return liga_live


async def get_odds_for_live_fixture(fixture_id: int) -> Dict:
    """
    Busca odds do fixture AO VIVO (live) pela API de odds.
    """
    async with httpx.AsyncClient(
        base_url=API_FOOTBALL_BASE_URL, headers=HEADERS, timeout=20
    ) as client:
        r = await client.get("/odds", params={"fixture": fixture_id, "bookmaker": 8})
        r.raise_for_status()
        return r.json()
