import os
from dotenv import load_dotenv

load_dotenv()

API_FOOTBALL_KEY = os.getenv("API_FOOTBALL_KEY", "")
API_FOOTBALL_HOST = "v3.football.api-sports.io"
API_FOOTBALL_BASE_URL = f"https://{API_FOOTBALL_HOST}"

LIGA_PORTUGAL_ID = 94

HISTORIC_SEASONS = [2020, 2021, 2022, 2023, 2024]

# Telegram
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# Limiar de edge para enviar alerta (ex: só avisar se edge >= 5%)
MIN_EDGE_ALERT = float(os.getenv("MIN_EDGE_ALERT", "0.05"))
