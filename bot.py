import os
import json
import asyncio
import logging
from typing import List, Dict, Set
from datetime import datetime, timezone

from dotenv import load_dotenv
from providers import get_provider, ProviderError

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import (
    Application, ApplicationBuilder, CommandHandler, ContextTypes,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("btc_top200_bot")

STATE_FILE = "top200_state.json"
CHATS_FILE = "chats.json"

def load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return default

def save_json(path: str, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    chats = load_json(CHATS_FILE, [])
    if chat_id not in chats:
        chats.append(chat_id)
        save_json(CHATS_FILE, chats)
    await update.message.reply_text(
        "Привет! Я буду присылать уведомления, если адрес попал в Топ‑200 или вышел из него.\n"
        "Команды:\n"
        "/now — показать текущий Топ‑200 (сводка)\n"
        "/status — показать параметры и подписанные чаты",
    )
    logger.info(f"/start by {user.id} in chat {chat_id}")

async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chats = load_json(CHATS_FILE, [])
    env = {
        "PROVIDER": os.getenv("PROVIDER"),
        "FETCH_INTERVAL_MIN": os.getenv("FETCH_INTERVAL_MIN"),
    }
    await update.message.reply_text(
        f"Провайдер: {env['PROVIDER']}\nИнтервал: {env['FETCH_INTERVAL_MIN']} мин\n"
        f"Подписанные чаты: {', '.join(map(str, chats)) if chats else 'нет'}"
    )

async def cmd_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    provider_name = os.getenv("PROVIDER", "bitinfocharts")
    provider = get_provider(provider_name)
    try:
        top200 = provider.get_top200()
    except ProviderError as e:
        await update.message.reply_text(f"Ошибка провайдера: {e}")
        return
    # Show quick summary
    sample = "\n".join([f"{r['rank']:>3}. {r['address']} ({r.get('balance_btc','?')} BTC)"
                        for r in top200[:20]])
    await update.message.reply_text(
        "Первые 20 адресов из текущего Топ‑200:\n" + sample
    )

async def notify(app: Application, text: str):
    chats = set(load_json(CHATS_FILE, []))
    # Also allow fixed chat IDs via env (comma‑separated)
    env_chats = os.getenv("NOTIFY_CHAT_IDS", "").strip()
    if env_chats:
        chats |= {int(cid) for cid in env_chats.split(",") if cid.strip().isdigit()}
    if not chats:
        logger.info("Нет подписанных чатов для отправки уведомления.")
        return
    for cid in chats:
        try:
            await app.bot.send_message(cid, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception as e:
            logger.error(f"Не удалось отправить сообщение в чат {cid}: {e}")

def ranks_set(top: List[Dict]) -> Set[str]:
    return {r["address"] for r in top}

def fmt_entry(r: Dict) -> str:
    rank = r.get("rank", "?")
    addr = r["address"]
    bal = r.get("balance_btc")
    bal_str = f"{bal:.8f} BTC" if isinstance(bal, (int, float)) else "—"
    return f"#{rank} <code>{addr}</code> ({bal_str})"

async def check_once(app: Application):
    provider_name = os.getenv("PROVIDER", "bitinfocharts")
    try:
        provider = get_provider(provider_name)
        top_now = provider.get_top200()
    except ProviderError as e:
        logger.error(f"Provider error: {e}")
        return

    old_state = load_json(STATE_FILE, {})
    old_list = old_state.get("top200", [])
    old_by_addr = {r["address"]: r for r in old_list}

    now_set = ranks_set(top_now)
    old_set = ranks_set(old_list)

    entered_addrs = list(now_set - old_set)
    exited_addrs  = list(old_set - now_set)

    # Build messages
    if entered_addrs or exited_addrs:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        lines = [f"<b>Изменения Топ‑200 BTC</b> • {ts}"]
        if entered_addrs:
            lines.append("<b>Новые в Топ‑200:</b>")
            for a in entered_addrs[:50]:
                r = next((x for x in top_now if x["address"] == a), {"address": a})
                lines.append("• " + fmt_entry(r))
            if len(entered_addrs) > 50:
                lines.append(f"…и ещё {len(entered_addrs)-50}")
        if exited_addrs:
            lines.append("<b>Вышли из Топ‑200:</b>")
            for a in exited_addrs[:50]:
                r = old_by_addr.get(a, {"address": a})
                lines.append("• " + fmt_entry(r))
            if len(exited_addrs) > 50:
                lines.append(f"…и ещё {len(exited_addrs)-50}")
        await notify(app, "\n".join(lines))
    else:
        logger.info("Изменений Топ‑200 нет.")

    # Save current snapshot
    save_json(STATE_FILE, {"top200": top_now})

async def scheduler(app: Application):
    interval_min = int(os.getenv("FETCH_INTERVAL_MIN", "10"))
    # Initial delay to avoid spamming on launch
    await asyncio.sleep(2)
    while True:
        try:
            await check_once(app)
        except Exception as e:
            logger.exception(f"Ошибка в check_once: {e}")
        await asyncio.sleep(interval_min * 60)

async def main():
    load_dotenv()
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN не задан в .env")

    application: Application = ApplicationBuilder().token(token).build()

    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("status", cmd_status))
    application.add_handler(CommandHandler("now", cmd_now))

    async with application:
        # Kick off scheduler loop
        asyncio.create_task(scheduler(application))
        await application.start()
        logger.info("Bot started. Press Ctrl+C to stop.")
        await application.updater.start_polling()
        # Keep running until stopped
        await application.wait_closed()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Stopped by user")
