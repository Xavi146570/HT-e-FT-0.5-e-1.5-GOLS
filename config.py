import os
from dotenv import load_dotenv

load_dotenv()

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY")
API_FOOTBALL_HOST = "v3.football.api-sports.io"
API_FOOTBALL_BASE_URL = f"https://{API_FOOTBALL_HOST}"

# Id da Liga Portugal na API-FOOTBALL (Primeira Liga normalmente é 94, mas confirme na docs/endpoint leagues)
LIGA_PORTUGAL_ID = 94

# Temporadas que você quer usar como histórico
HISTORIC_SEASONS = [2020, 2021, 2022, 2023, 2024]
