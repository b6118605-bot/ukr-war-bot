import html
import logging
import os
from typing import Dict, List, Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
)

from config import ADMIN_ID, FACTIONS, MAX_PLAYERS, REGIONS, SHOP_ITEMS, TOKEN
from database import Database
from game_engine import WarEngine
from map_generator import BattleVisualizer

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("war_bot")

# UTF-8 safe deterministic order for region ids in callback_data.
REGION_ORDER = list(REGIONS.keys())
REGION_ID = {name: idx for idx, name in enumerate(REGION_ORDER)}

SELECT_FACTION = 0


db = Database()
vis = BattleVisualizer()
engine = WarEngine(db, vis)


def get_faction_emoji(faction_name: str) -> str:
    return FACTIONS.get(faction_name, "🏳️")


def region_from_id(region_id: str) -> Optional[str]:
    try:
        idx = int(region_id)
    except ValueError:
        return None
    if 0 <= idx < len(REGION_ORDER):
        return REGION_ORDER[idx]
    return None


def safe_username(user) -> str:
    return user.username or user.first_name or f"user_{user.id}"


async def send_text(
    update: Update,
    text: str,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    edit: bool = False,
) -> None:
    query = update.callback_query
    if query:
        if edit:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        else:
            await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        return

    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


def menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⚔️ Атаковать", callback_data="menu:attack"),
                InlineKeyboardButton("🛒 Магазин", callback_data="menu:shop"),
            ],
            [
                InlineKeyboardButton("♻️ Собрать ресурсы", callback_data="menu:collect"),
                InlineKeyboardButton("😴 Отдых", callback_data="menu:rest"),
            ],
            [
                InlineKeyboardButton("🗺️ Карта", callback_data="menu:map"),
                InlineKeyboardButton("🏆 Рейтинг", callback_data="menu:rating"),
            ],
            [
                InlineKeyboardButton("📰 События", callback_data="menu:log"),
                InlineKeyboardButton("📚 Помощь", callback_data="menu:help"),
            ],
        ]
    )


def get_available_factions() -> List[str]:
    occupied = set(db.get_occupied_factions())
    return [f for f in REGION_ORDER if f in FACTIONS and f not in occupied]


def available_faction_buttons() -> InlineKeyboardMarkup:
    available = get_available_factions()

    rows: List[List[InlineKeyboardButton]] = []
    row: List[InlineKeyboardButton] = []
    for i, faction in enumerate(available, start=1):
        icon = get_faction_emoji(faction)
        cb = f"fsel:{REGION_ID[faction]}"
        row.append(InlineKeyboardButton(f"{icon} {faction}", callback_data=cb))
        if i % 2 == 0:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    return InlineKeyboardMarkup(rows)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return ConversationHandler.END

    player = db.get_player(user.id)
    if player:
        await show_main_menu(update, context)
        return ConversationHandler.END

    if db.get_player_count() >= MAX_PLAYERS:
        await send_text(
            update,
            "❌ <b>Все области заняты.</b>\n\n"
            "Максимум 24 игрока. Подожди, пока какая-то область освободится.",
            edit=False,
        )
        return ConversationHandler.END

    keyboard = available_faction_buttons()
    if not keyboard.inline_keyboard:
        await send_text(update, "❌ Сейчас нет свободных областей.")
        return ConversationHandler.END

    available_count = len(get_available_factions())
    await send_text(
        update,
        f"⚔️ <b>Добро пожаловать, {html.escape(user.first_name or 'командир')}!</b>\n\n"
        f"Свободных областей: <b>{available_count}/{MAX_PLAYERS}</b>\n"
        "Выбери область для старта:",
        reply_markup=keyboard,
        edit=False,
    )
    return SELECT_FACTION


async def select_faction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return ConversationHandler.END

    await query.answer()
    payload = (query.data or "").split(":", maxsplit=1)
    if len(payload) != 2:
        await query.edit_message_text("❌ Некорректный выбор.")
        return ConversationHandler.END

    faction = region_from_id(payload[1])
    user = update.effective_user
    if not user or not faction:
        await query.edit_message_text("❌ Область не найдена.")
        return ConversationHandler.END

    if faction in db.get_occupied_factions():
        await query.edit_message_text("❌ Эту область только что заняли. Выбери другую через /start")
        return ConversationHandler.END

    try:
        db.create_player(user.id, safe_username(user), faction)
    except ValueError as exc:
        await query.edit_message_text(f"❌ {exc}")
        return ConversationHandler.END

    await query.edit_message_text(
        f"✅ <b>Ты командир области {get_faction_emoji(faction)} {faction}</b>\n\n"
        f"🏛️ Столица: <b>{html.escape(REGIONS[faction][0])}</b>\n"
        f"🗺️ Под контролем: <b>{len(REGIONS[faction])}</b> районов\n\n"
        "Открой /menu для управления.",
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    help_text = (
        "📚 <b>СПРАВКА WARBOT</b>\n\n"
        "<b>Цель:</b> контролировать фронт, экономику и удержание регионов.\n"
        "<b>Фронт:</b> атака возможна только по соседним областям.\n"
        "<b>Усталость:</b> каждый бой повышает усталость, на 100% атаки блокируются.\n"
        "<b>Партизаны:</b> на оккупированных землях снижается доход, растут риски.\n"
        "<b>Логистика:</b> растянутый фронт и низкое снабжение режут боевую мощь.\n\n"
        "Команды: /menu /attack /shop /collect /rest /map /rating /log /help"
    )
    await send_text(update, help_text, edit=bool(update.callback_query))


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    player = db.get_player(user.id)
    if not player:
        await send_text(update, "Сначала зарегистрируйся: /start", edit=bool(update.callback_query))
        return

    res = player["resources"]
    territories = db.get_territories(owner_id=user.id)

    text = (
        f"<b>{get_faction_emoji(player['faction'])} {html.escape(player['faction'])}</b> | "
        f"Командир: <b>{html.escape(player['username'])}</b>\n"
        f"{'─' * 38}\n"
        f"👥 Личный состав: <code>{res.get('manpower', 0):,}</code>\n"
        f"📦 Боеприпасы: <code>{res.get('ammo', 0):,}</code>\n"
        f"⛽ Топливо: <code>{res.get('fuel', 0):,}</code>\n"
        f"💰 Деньги: <code>{res.get('money', 0):,}</code>\n"
        f"🛡️ Танки: <code>{res.get('tanks', 0)}</code> | 🔥 Арта: <code>{res.get('artillery', 0)}</code>\n"
        f"💪 Мораль: <code>{res.get('morale', 100)}%</code>\n"
        f"😴 Усталость: <code>{player.get('war_fatigue', 0)}%</code>\n"
        f"🗺️ Территорий: <code>{len(territories)}</code>\n"
        f"🏆 Побед: <code>{player.get('wins', 0)}</code> | Поражений: <code>{player.get('losses', 0)}</code>\n"
        f"{'─' * 38}"
    )

    await send_text(update, text, reply_markup=menu_keyboard(), edit=bool(update.callback_query))


async def attack_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    player = db.get_player(update.effective_user.id)
    if not player:
        if update.callback_query:
            await update.callback_query.answer()
        await send_text(update, "Сначала /start", edit=bool(update.callback_query))
        return

    if player.get("war_fatigue", 0) >= 100:
        if update.callback_query:
            await update.callback_query.answer("❌ Армия истощена. Используй /rest", show_alert=True)
        else:
            await send_text(update, "❌ Армия истощена. Используй /rest")
        return

    if update.callback_query:
        await update.callback_query.answer()

    regions = engine.get_attackable_regions(update.effective_user.id)
    if not regions:
        await send_text(update, "❌ Нет доступных целей на линии фронта.", edit=bool(update.callback_query))
        return

    keyboard = []
    for item in regions:
        region = item["region"]
        rid = REGION_ID.get(region)
        if rid is None:
            continue
        label = f"{get_faction_emoji(region)} {region} ({item['targets']} целей)"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"atkreg:{rid}")])

    keyboard.append([InlineKeyboardButton("« Назад", callback_data="menu:back")])
    text = (
        "<b>⚔️ ВЫБОР ОБЛАСТИ ДЛЯ АТАКИ</b>\n\n"
        "Можно атаковать только соседние области (линия фронта).\n"
        "Выбери область, затем конкретный район."
    )

    await send_text(
        update,
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        edit=bool(update.callback_query),
    )


async def select_attack_region(update: Update, context: ContextTypes.DEFAULT_TYPE, region_id: str):
    if update.callback_query:
        await update.callback_query.answer()
    region = region_from_id(region_id)
    if not region:
        await send_text(update, "❌ Область не найдена.", edit=True)
        return

    context.user_data["attack_region"] = region
    targets = db.get_attack_targets_for_region(update.effective_user.id, region)
    if not targets:
        await send_text(update, "❌ В этой области нет доступных целей.", edit=True)
        return

    keyboard = []
    for target in targets:
        owner = db.get_player(target["owner_id"]) if target.get("owner_id") else None
        if owner:
            label = f"🔴 {target['district']} ({owner['username']})"
        else:
            label = f"🟢 {target['district']} (свободно)"
        keyboard.append([InlineKeyboardButton(label, callback_data=f"atkdist:{target['id']}")])

    keyboard.append([InlineKeyboardButton("« К областям", callback_data="menu:attack")])

    await send_text(
        update,
        f"<b>⚔️ Районы {get_faction_emoji(region)} {region}</b>\n\nВыбери цель:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        edit=True,
    )


async def confirm_attack(update: Update, context: ContextTypes.DEFAULT_TYPE, territory_id: str):
    if update.callback_query:
        await update.callback_query.answer()
    try:
        tid = int(territory_id)
    except ValueError:
        await send_text(update, "❌ Некорректная цель.", edit=True)
        return

    target = db.get_territory_by_id(tid)
    if not target:
        await send_text(update, "❌ Цель уже недоступна.", edit=True)
        return

    context.user_data["attack_target_id"] = tid
    context.user_data["attack_region"] = target["region"]
    context.user_data["attack_district"] = target["district"]

    rid = REGION_ID.get(target["region"], 0)
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("✅ НАЧАТЬ ШТУРМ", callback_data="atkgo")],
            [InlineKeyboardButton("« Отмена", callback_data=f"atkreg:{rid}")],
        ]
    )

    await send_text(
        update,
        f"<b>⚔️ ПОДГОТОВКА К БОЮ</b>\n\n"
        f"🎯 Цель: <b>{target['district']}</b>\n"
        f"📍 Область: <b>{target['region']}</b>\n"
        f"🛡️ Защита: <b>{target.get('defense', 0)}</b>\n"
        f"🏗️ Укрепления: <b>{target.get('fortification', 0)}</b>\n"
        f"🕵️ Партизаны: <b>{target.get('partisan', 0)}%</b>",
        reply_markup=keyboard,
        edit=True,
    )


async def execute_attack(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query:
        await query.answer("⚔️ Бой начался...")

    district = context.user_data.get("attack_district")
    region = context.user_data.get("attack_region")
    if not district or not region:
        await send_text(update, "❌ Цель не выбрана.", edit=True)
        return

    result = engine.attack(update.effective_user.id, district, region)

    if result.image_path and os.path.exists(result.image_path):
        with open(result.image_path, "rb") as photo:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo,
                caption=f"<b>📸 БОЕВАЯ СВОДКА</b>\n\n{result.message}",
                parse_mode=ParseMode.HTML,
            )
        try:
            os.remove(result.image_path)
        except OSError:
            logger.warning("Не удалось удалить %s", result.image_path)
    else:
        await send_text(update, result.message, edit=False)

    await show_main_menu(update, context)


async def shop_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    player = db.get_player(update.effective_user.id)
    if not player:
        await send_text(update, "Сначала /start", edit=bool(update.callback_query))
        return

    res = player["resources"]
    text = (
        f"<b>🛒 ВОЕННЫЙ МАГАЗИН</b>\n\n"
        f"💰 {res.get('money', 0)} | 👥 {res.get('manpower', 0)} | "
        f"📦 {res.get('ammo', 0)} | ⛽ {res.get('fuel', 0)}\n\n"
        f"<i>Выбери покупку:</i>"
    )

    keyboard = []
    for key, item in SHOP_ITEMS.items():
        price = " ".join(f"{res_name[:3]}:{val}" for res_name, val in item["price"].items())
        keyboard.append([InlineKeyboardButton(f"{item['name']} [{price}]", callback_data=f"buy:{key}")])
    keyboard.append([InlineKeyboardButton("« Назад", callback_data="menu:back")])

    await send_text(
        update,
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        edit=bool(update.callback_query),
    )


async def buy_item(update: Update, context: ContextTypes.DEFAULT_TYPE, item_key: str):
    query = update.callback_query
    success, message = engine.buy_item(update.effective_user.id, item_key)

    if query:
        await query.answer(message, show_alert=True)
    else:
        await send_text(update, message)

    await shop_menu(update, context)


async def collect_resources(update: Update, context: ContextTypes.DEFAULT_TYPE):
    result = engine.collect_resources(update.effective_user.id)
    if "error" in result:
        if update.callback_query:
            await update.callback_query.answer(result["error"], show_alert=True)
            await show_main_menu(update, context)
        else:
            await send_text(update, result["error"])
        return

    text = (
        f"♻️ Сбор завершен\n"
        f"👥 +{result['manpower']} | 📦 +{result['ammo']} | ⛽ +{result['fuel']} | 💰 +{result['money']}"
    )

    if update.callback_query:
        await update.callback_query.answer(text, show_alert=True)
        await show_main_menu(update, context)
    else:
        await send_text(update, text)


async def rest_army(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = engine.rest_army(update.effective_user.id)
    if update.callback_query:
        await update.callback_query.answer(msg, show_alert=True)
        await show_main_menu(update, context)
    else:
        await send_text(update, msg)


async def show_map(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    player = db.get_player(update.effective_user.id)
    if not player:
        await send_text(update, "Сначала /start", edit=bool(update.callback_query))
        return

    territories = db.get_territories(owner_id=update.effective_user.id)
    if not territories:
        await send_text(update, "❌ У тебя нет территорий.", edit=bool(update.callback_query))
        return

    map_path = vis.generate_territory_map(
        update.effective_user.id,
        player["username"],
        player["faction"],
        territories,
    )

    with open(map_path, "rb") as photo:
        await context.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=photo,
            caption=(
                f"<b>🗺️ КАРТА ВЛАДЕНИЙ</b>\n"
                f"{html.escape(player['username'])} | {len(territories)} районов"
            ),
            parse_mode=ParseMode.HTML,
        )

    try:
        os.remove(map_path)
    except OSError:
        logger.warning("Не удалось удалить %s", map_path)

    if update.callback_query:
        await show_main_menu(update, context)


async def show_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    leaders = db.get_leaderboard()
    if not leaders:
        text = "🏆 Рейтинг пока пуст"
    else:
        lines = ["<b>🏆 ТОП КОМАНДИРОВ</b>", ""]
        for i, p in enumerate(leaders, start=1):
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}."
            lines.append(
                f"{medal} <b>{html.escape(p['username'])}</b> ({html.escape(p['faction'])}) | "
                f"🏆 {p['wins']} | 🗺️ {p['territories']}"
            )
        text = "\n".join(lines)

    markup = InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data="menu:back")]]) if update.callback_query else None
    await send_text(update, text, reply_markup=markup, edit=bool(update.callback_query))


async def show_log(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    logs = db.get_war_log(8)
    if logs:
        text = "<b>📰 ПОСЛЕДНИЕ СОБЫТИЯ</b>\n\n" + "\n".join(f"• {html.escape(item)}" for item in logs)
    else:
        text = "Пока нет событий"

    markup = InlineKeyboardMarkup([[InlineKeyboardButton("« Назад", callback_data="menu:back")]]) if update.callback_query else None
    await send_text(update, text, reply_markup=markup, edit=bool(update.callback_query))


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return

    data = query.data or ""

    if data == "menu:attack":
        await attack_menu(update, context)
    elif data.startswith("atkreg:"):
        await select_attack_region(update, context, data.split(":", maxsplit=1)[1])
    elif data.startswith("atkdist:"):
        await confirm_attack(update, context, data.split(":", maxsplit=1)[1])
    elif data == "atkgo":
        await execute_attack(update, context)
    elif data == "menu:shop":
        await shop_menu(update, context)
    elif data.startswith("buy:"):
        await buy_item(update, context, data.split(":", maxsplit=1)[1])
    elif data == "menu:collect":
        await collect_resources(update, context)
    elif data == "menu:rest":
        await rest_army(update, context)
    elif data == "menu:map":
        await show_map(update, context)
    elif data == "menu:rating":
        await show_rating(update, context)
    elif data == "menu:log":
        await show_log(update, context)
    elif data == "menu:help":
        await help_command(update, context)
    elif data == "menu:back":
        await show_main_menu(update, context)


async def rest_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await rest_army(update, context)


async def log_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_log(update, context)


async def attack_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await attack_menu(update, context)


async def shop_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await shop_menu(update, context)


async def collect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await collect_resources(update, context)


async def map_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_map(update, context)


async def rating_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_rating(update, context)


def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN не задан. Укажи переменную окружения BOT_TOKEN.")

    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={SELECT_FACTION: [CallbackQueryHandler(select_faction, pattern=r"^fsel:")]},
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("menu", show_main_menu))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("rest", rest_command))
    application.add_handler(CommandHandler("log", log_command))
    application.add_handler(CommandHandler("attack", attack_command))
    application.add_handler(CommandHandler("shop", shop_command))
    application.add_handler(CommandHandler("collect", collect_command))
    application.add_handler(CommandHandler("map", map_command))
    application.add_handler(CommandHandler("rating", rating_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    logger.info("WarBot started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
