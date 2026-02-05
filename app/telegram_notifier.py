import httpx
from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID


async def send_telegram_message(message: str) -> bool:
    """
    Envia uma mensagem formatada para o grupo do Telegram configurado.
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram não configurado: falta TELEGRAM_BOT_TOKEN ou TELEGRAM_CHAT_ID nas variáveis de ambiente.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
            return True
    except Exception as e:
        print(f"❌ Erro ao enviar mensagem para o Telegram: {e}")
        return False


def format_alert_message(
    home_team: str,
    away_team: str,
    market: str,
    p_min: float,
    p_market: float,
    edge: float,
    odd: float,
) -> str:
    """
    Formata o texto do alerta com emojis e negritos para facilitar a leitura no telemóvel.
    """
    # Usa um emoji de fogo se a vantagem (edge) for superior a 10%
    emoji = "🔥" if edge >= 0.10 else "✅"
    
    msg = f"""
{emoji} <b>VALOR ENCONTRADO</b> {emoji}

🏟 <b>{home_team}</b> vs <b>{away_team}</b>
📊 Mercado: <b>{market}</b>

🎯 P(modelo conservador): <b>{p_min:.1%}</b>
📉 P(mercado): <b>{p_market:.1%}</b>
💰 Edge: <b>{edge:+.1%}</b>

🎲 Odd Atual: <b>{odd:.2f}</b>

⚠️ <i>Analisa as escalações antes de entrar!</i>
"""
    return msg.strip()
