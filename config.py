import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ASSETS_DIR = Path(os.getenv("ASSETS_DIR", str(BASE_DIR / "assets")))
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "war_game.db"))

TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", "0"))

# Free image generation endpoint (no API key required for basic use)
IMAGE_API = os.getenv("IMAGE_API", "https://image.pollinations.ai/prompt/")

START_RESOURCES = {
    "manpower": 1000,
    "ammo": 500,
    "fuel": 300,
    "tanks": 10,
    "artillery": 5,
    "morale": 100,
}

REGIONS = {
    "Донецкая": ["Мариуполь", "Бахмут", "Авдеевка", "Краматорск"],
    "Луганская": ["Северодонецк", "Лисичанск", "Рубежное"],
    "Харьковская": ["Изюм", "Купянск", "Балаклея"],
    "Запорожская": ["Мелитополь", "Энергодар", "Токмак"],
    "Херсонская": ["Херсон", "Новая Каховка", "Скадовск"],
}
