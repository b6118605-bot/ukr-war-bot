import html
import logging
import os
from datetime import timedelta

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
)

from config import ADMIN_ID, TOKEN
from database import Database
from game_engine import WarEngine
from map_generator import BattleVisualizer

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("war_bot")

db = Database()
vis = BattleVisualizer()
engine = WarEngine(db, vis)

SELECT_FACTION = 0


def main_menu_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Атаковать район", callback_data="action_attack")],
            [InlineKeyboardButton("Мои территории", callback_data="action_map")],
            [InlineKeyboardButton("Рейтинг", callback_data="action_rating")],
            [InlineKeyboardButton("Сбор ресурсов", callback_data="action_collect")],
        ]
    )


async def _safe_edit_or_send(update: Update, text: str, reply_markup: InlineKeyboardMarkup | None = None) -> None:
    query = update.callback_query
    if query:
        try:
            await query.edit_message_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            return
        except Exception:
            if query.message:
                await query.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
            return
    if update.message:
        await update.message.reply_text(text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return ConversationHandler.END

    player = db.get_player(user.id)
    if player:
        await show_main_menu(update, context)
        return ConversationHandler.END

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Синие", callback_data="faction_blue")],
            [InlineKeyboardButton("Красные", callback_data="faction_red")],
            [InlineKeyboardButton("Желтые", callback_data="faction_yellow")],
        ]
    )
    text = (
        f"Добро пожаловать, {html.escape(user.first_name or 'командир')}.\n\n"
        f"Выбери фракцию, чтобы начать игру."
    )
    await _safe_edit_or_send(update, text, keyboard)
    return SELECT_FACTION


async def select_faction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return ConversationHandler.END
    await query.answer()

    faction_map = {
        "faction_blue": "Синие",
        "faction_red": "Красные",
        "faction_yellow": "Желтые",
    }
    faction = faction_map.get(query.data, "Нейтралы")
    user = update.effective_user
    if not user:
        return ConversationHandler.END

    db.create_player(user.id, user.username or user.first_name or f"user_{user.id}", faction)
    await query.edit_message_text(
        f"Фракция выбрана: <b>{html.escape(faction)}</b>.\nИспользуй /menu для управления.",
        parse_mode=ParseMode.HTML,
    )
    return ConversationHandler.END


async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user:
        return

    player = db.get_player(user.id)
    if not player:
        await _safe_edit_or_send(update, "Сначала запусти регистрацию: /start")
        return

    res = player["resources"]
    territories = db.get_territories(user.id)
    username = html.escape(player["username"] or f"user_{user.id}")
    faction = html.escape(player["faction"] or "Не указано")

    text = (
        f"<b>{faction}</b> | {username}\n"
        f"------------------------------\n"
        f"Личный состав: <code>{res.get('manpower', 0)}</code>\n"
        f"Боеприпасы: <code>{res.get('ammo', 0)}</code>\n"
        f"Топливо: <code>{res.get('fuel', 0)}</code>\n"
        f"Танки: <code>{res.get('tanks', 0)}</code> | Артиллерия: <code>{res.get('artillery', 0)}</code>\n"
        f"Мораль: <code>{res.get('morale', 100)}%</code>\n"
        f"Территорий: <code>{len(territories)}</code>\n"
        f"------------------------------"
    )
    await _safe_edit_or_send(update, text, main_menu_markup())


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query:
        return
    await query.answer()

    user = update.effective_user
    if not user:
        return

    data = query.data or ""

    if data == "action_attack":
        targets = engine.get_available_targets(user.id)
        if not targets:
            await query.edit_message_text("Нет доступных целей.")
            return

        keyboard = []
        for terr in targets:
            btn = f"{terr['district']} ({terr['region']})"
            keyboard.append([InlineKeyboardButton(btn, callback_data=f"attack_{terr['id']}")])
        keyboard.append([InlineKeyboardButton("Назад", callback_data="back_menu")])
        await query.edit_message_text(
            "Выбери район для штурма:",
            reply_markup=InlineKeyboardMarkup(keyboard),
        )
        return

    if data.startswith("attack_"):
        try:
            target_id = int(data.split("_", maxsplit=1)[1])
        except ValueError:
            await query.edit_message_text("Некорректная цель.")
            return

        territory = db.get_territory_by_id(target_id)
        if not territory:
            await query.edit_message_text("Цель больше не доступна.")
            return

        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("Начать штурм", callback_data=f"confirm_attack_{target_id}")],
                [InlineKeyboardButton("Отмена", callback_data="action_attack")],
            ]
        )
        await query.edit_message_text(
            f"Подтвердить атаку на {territory['district']} ({territory['region']})?\n"
            f"Будут потрачены боеприпасы и топливо.",
            reply_markup=keyboard,
        )
        return

    if data.startswith("confirm_attack_"):
        try:
            target_id = int(data.split("_", maxsplit=2)[2])
        except ValueError:
            await query.edit_message_text("Некорректный формат атаки.")
            return

        await query.edit_message_text("Бой идет. Формируется тактическая сводка...")
        result = engine.attack(user.id, target_id)

        if result.image_path and os.path.exists(result.image_path):
            with open(result.image_path, "rb") as photo:
                await context.bot.send_photo(
                    chat_id=update.effective_chat.id,
                    photo=photo,
                    caption=result.message,
                )
            try:
                os.remove(result.image_path)
            except OSError:
                logger.warning("Не удалось удалить временный файл %s", result.image_path)
        else:
            await context.bot.send_message(chat_id=update.effective_chat.id, text=result.message)

        await show_main_menu(update, context)
        return

    if data == "action_map":
        territories = db.get_territories(user.id)
        if not territories:
            await query.edit_message_text("У тебя пока нет территорий.")
            return

        map_path = vis.generate_territory_map(user.id, territories)
        with open(map_path, "rb") as photo:
            await context.bot.send_photo(
                chat_id=update.effective_chat.id,
                photo=photo,
                caption=f"Твои владения: {len(territories)}",
            )
        try:
            os.remove(map_path)
        except OSError:
            logger.warning("Не удалось удалить временный файл %s", map_path)

        lines = [f"{idx}. {t['district']} ({t['region']}) - защита {t['defense']}" for idx, t in enumerate(territories, 1)]
        lines.append("")
        lines.append("Нажми Назад, чтобы вернуться в меню.")
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_menu")]]),
        )
        return

    if data == "action_collect":
        ok, payload = engine.produce_resources(user.id, force=False)
        if ok:
            await query.edit_message_text(
                f"Ресурсы получены:\n"
                f"+{payload['manpower']} личного состава\n"
                f"+{payload['ammo']} боеприпасов\n"
                f"+{payload['fuel']} топлива"
            )
        else:
            wait_seconds = payload.get("wait_seconds", 0)
            wait_text = str(timedelta(seconds=wait_seconds))
            await query.edit_message_text(f"Сбор еще на кулдауне. Осталось: {wait_text}")
        await show_main_menu(update, context)
        return

    if data == "action_rating":
        all_territories = db.get_territories()
        score = {}
        for terr in all_territories:
            owner = terr["owner_id"]
            if owner:
                score[owner] = score.get(owner, 0) + 1
        top = sorted(score.items(), key=lambda x: x[1], reverse=True)[:10]

        if not top:
            text = "Рейтинг пока пуст."
        else:
            rows = ["ТОП ЗАХВАТЧИКОВ", ""]
            for idx, (uid, count) in enumerate(top, 1):
                player = db.get_player(uid)
                name = player["username"] if player and player["username"] else f"user_{uid}"
                rows.append(f"{idx}. {name} - {count}")
            text = "\n".join(rows)

        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Назад", callback_data="back_menu")]]),
        )
        return

    if data == "back_menu":
        await show_main_menu(update, context)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await show_main_menu(update, context)


async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not user or user.id != ADMIN_ID:
        if update.message:
            await update.message.reply_text("Доступ только для администратора.")
        return

    if context.args and context.args[0].lower() == "income":
        updated = engine.produce_resources_for_all()
        if update.message:
            await update.message.reply_text(f"Начислен пассивный доход для {updated} игроков.")
        return

    if update.message:
        await update.message.reply_text("Админ-панель: /admin income")


async def hourly_income_job(context: ContextTypes.DEFAULT_TYPE):
    updated = engine.produce_resources_for_all()
    logger.info("Hourly income applied to %s players", updated)


def main():
    if not TOKEN:
        raise RuntimeError("BOT_TOKEN не задан. Укажи переменную окружения BOT_TOKEN.")

    application = Application.builder().token(TOKEN).build()

    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={SELECT_FACTION: [CallbackQueryHandler(select_faction, pattern=r"^faction_")]},
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("menu", show_main_menu))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("admin", admin_panel))
    application.add_handler(CallbackQueryHandler(button_handler))

    if application.job_queue:
        application.job_queue.run_repeating(hourly_income_job, interval=3600, first=3600)
    else:
        logger.warning("Job queue недоступен. Почасовой пассивный доход отключен.")

    logger.info("War bot started")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
