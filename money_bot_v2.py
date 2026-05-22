#!/usr/bin/env python3
"""
💰 PayWay ABA Money Tracker — Combined Bot
- UserBot (Telethon): listens silently for PayWay messages
- Calculationsbot (python-telegram-bot): handles /today /week etc commands
- Both run together in ONE terminal
"""

import re
import json
import os
import logging
import asyncio
from datetime import datetime, time
from zoneinfo import ZoneInfo

from telethon import TelegramClient, events
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, MessageHandler,
    CommandHandler, CallbackQueryHandler, filters,
)

# ── SETTINGS ──────────────────────────────────────────────────────────────────
import os
API_ID    = int(os.environ.get("API_ID", "36474508"))
API_HASH  = os.environ.get("API_HASH", "86a53c87962052aca9e4a28f7aa327d8")
PHONE     = os.environ.get("PHONE", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
# ─────────────────────────────────────────────────────────────────────────────

TIMEZONE  = "Asia/Phnom_Penh"
DATA_FILE = "group_totals.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ── Data ──────────────────────────────────────────────────────────────────────
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_chat(data, chat_id):
    cid = str(chat_id)
    if cid not in data:
        data[cid] = {"history": []}
    if "history" not in data[cid]:
        data[cid]["history"] = []
    return data[cid]

def now_kh():
    return datetime.now(ZoneInfo(TIMEZONE))

def fmt_usd(amount):
    return f"${amount:,.2f}"

def fmt_khr(amount):
    return f"៛{int(amount):,}"

# ── PayWay detection ──────────────────────────────────────────────────────────
def is_payway_message(text):
    return (
        ("paid by" in text and "Trx. ID" in text) or
        ("paid by" in text and "APV:" in text) or
        ("paid by" in text and "ABA" in text) or
        ("Trx. ID" in text and ("$" in text or "៛" in text))
    )

def parse_payway(text):
    usd = re.search(r"\$\s*(\d+(?:\.\d+)?)", text)
    if usd:
        return float(usd.group(1)), "USD"
    khr = re.search(r"[៛]\s*(\d[\d,]*)", text)
    if khr:
        return int(khr.group(1).replace(",", "")), "KHR"
    return None, None

def parse_amount(text):
    text = text.strip()
    m = re.match(r"^([+-]?)\s*([៛$]?)\s*(\d[\d,]*(?:\.\d+)?)$", text)
    if m:
        sign_str, sym, num = m.groups()
        sign = -1 if sign_str == "-" else 1
        num = float(num.replace(",", ""))
        if sym == "៛":
            return int(num) * sign, "KHR"
        else:
            return num * sign, "USD"
    m2 = re.match(r"^([+-]?)\s*(\d[\d,]*(?:\.\d+)?)\s*([៛$])$", text)
    if m2:
        sign_str, num, sym = m2.groups()
        sign = -1 if sign_str == "-" else 1
        num = float(num.replace(",", ""))
        if sym == "៛":
            return int(num) * sign, "KHR"
        else:
            return num * sign, "USD"
    return None, None

# ── Summary ───────────────────────────────────────────────────────────────────
def filter_history(history, period):
    now = now_kh()
    result = []
    for e in history:
        try:
            dt = datetime.fromisoformat(e["datetime"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo(TIMEZONE))
            if period == "today" and dt.date() == now.date():
                result.append(e)
            elif period == "week" and dt.isocalendar()[:2] == now.isocalendar()[:2]:
                result.append(e)
            elif period == "month" and dt.year == now.year and dt.month == now.month:
                result.append(e)
            elif period == "all":
                result.append(e)
        except:
            result.append(e)
    return result

def build_summary(chat_id, period, label_en, label_km):
    data = load_data()
    chat = get_chat(data, str(chat_id))
    history = filter_history(chat["history"], period)
    usd = sum(e["amount"] for e in history if e["currency"] == "USD")
    khr = sum(int(e["amount"]) for e in history if e["currency"] == "KHR")
    now = now_kh().strftime("%d/%m/%Y %H:%M")
    return (
        f"📊 *{label_en} / {label_km}*\n"
        f"🕐 {now}\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"💵 USD: `{fmt_usd(usd)}`\n"
        f"💴 KHR: `{fmt_khr(khr)}`\n\n"
        f"📋 Transactions: `{len(history)}`\n"
        f"━━━━━━━━━━━━━━━━"
    )

# ══════════════════════════════════════════════════════════════════════════════
# PART 1: Telethon UserBot — silently saves PayWay messages
# ══════════════════════════════════════════════════════════════════════════════
# Use StringSession from env if available, otherwise use file
SESSION_STRING = os.environ.get("SESSION_STRING", "")
if SESSION_STRING:
    from telethon.sessions import StringSession
    userbot = TelegramClient(StringSession(SESSION_STRING), API_ID, API_HASH)
else:
    userbot = TelegramClient("userbot_session", API_ID, API_HASH)

@userbot.on(events.NewMessage())
async def userbot_handler(event):
    text = event.raw_text or ""
    if not text.strip() or not is_payway_message(text):
        return
    chat_id = str(event.chat_id)
    sender = await event.get_sender()
    sender_name = getattr(sender, "first_name", None) or getattr(sender, "title", None) or "PayWay"
    amount, currency = parse_payway(text)
    if amount:
        data = load_data()
        get_chat(data, chat_id)["history"].append({
            "user": sender_name,
            "amount": amount,
            "currency": currency,
            "source": "PayWay",
            "datetime": now_kh().isoformat()
        })
        save_data(data)
        logger.info(f"✅ PayWay {amount} {currency} from '{sender_name}' in {chat_id}")

# ══════════════════════════════════════════════════════════════════════════════
# PART 2: Calculationsbot — handles commands
# ══════════════════════════════════════════════════════════════════════════════
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 *PayWay Money Tracker*\n\n"
        "📋 *Commands:*\n"
        "• `/today` — Today / ថ្ងៃនេះ\n"
        "• `/week` — This week / សប្តាហ៍នេះ\n"
        "• `/month` — This month / ខែនេះ\n"
        "• `/total` — All time / សរុបទាំងអស់\n"
        "• `/summary` — Pick period 📅\n"
        "• `/history` — Last 10 entries\n"
        "• `/reset` — Reset this group\n"
        "• `/setreport` — Set auto report time 🕐",
        parse_mode="Markdown"
    )

async def today_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_summary(update.effective_chat.id, "today", "Today", "ថ្ងៃនេះ"), parse_mode="Markdown")

async def week_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_summary(update.effective_chat.id, "week", "This Week", "សប្តាហ៍នេះ"), parse_mode="Markdown")

async def month_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_summary(update.effective_chat.id, "month", "This Month", "ខែនេះ"), parse_mode="Markdown")

async def total_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(build_summary(update.effective_chat.id, "all", "All Time", "សរុបទាំងអស់"), parse_mode="Markdown")

async def reset_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    data[str(update.effective_chat.id)] = {"history": []}
    save_data(data)
    await update.message.reply_text("🔄 *Reset done!*", parse_mode="Markdown")

async def history_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    chat = get_chat(data, str(update.effective_chat.id))
    history = chat["history"]
    if not history:
        await update.message.reply_text("📭 No entries yet.")
        return
    last_10 = history[-10:]
    lines = []
    for e in reversed(last_10):
        amt = fmt_usd(e["amount"]) if e["currency"] == "USD" else fmt_khr(e["amount"])
        sign = "+" if e["amount"] >= 0 else ""
        dt = e.get("datetime", "")[:16].replace("T", " ")
        lines.append(f"• `{sign}{amt}` — {e['user']} _{e.get('source','manual')}_ `{dt}`")
    usd = sum(e["amount"] for e in history if e["currency"] == "USD")
    khr = sum(int(e["amount"]) for e in history if e["currency"] == "KHR")
    await update.message.reply_text(
        f"📋 *Last {len(last_10)} entries:*\n\n" + "\n".join(lines) +
        f"\n\n💵 USD Total: `{fmt_usd(usd)}`\n💴 KHR Total: `{fmt_khr(khr)}`",
        parse_mode="Markdown"
    )

async def summary_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("📅 Today / ថ្ងៃនេះ", callback_data="sum_today"),
        InlineKeyboardButton("📆 This Week / សប្តាហ៍នេះ", callback_data="sum_week"),
    ],[
        InlineKeyboardButton("🗓 This Month / ខែនេះ", callback_data="sum_month"),
        InlineKeyboardButton("📊 All Time / សរុប", callback_data="sum_all"),
    ]]
    await update.message.reply_text("📅 *Choose period:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data_map = {
        "sum_today": ("today", "Today", "ថ្ងៃនេះ"),
        "sum_week":  ("week", "This Week", "សប្តាហ៍នេះ"),
        "sum_month": ("month", "This Month", "ខែនេះ"),
        "sum_all":   ("all", "All Time", "សរុបទាំងអស់"),
    }
    period, label_en, label_km = data_map.get(query.data, ("all", "All Time", "សរុប"))
    await query.edit_message_text(build_summary(query.message.chat.id, period, label_en, label_km), parse_mode="Markdown")

async def handle_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (update.message.text or "").strip()
    amount, currency = parse_amount(text)
    if amount is not None:
        chat_id = str(update.effective_chat.id)
        user = update.effective_user.first_name or "Unknown"
        data = load_data()
        get_chat(data, chat_id)["history"].append({
            "user": user, "amount": amount,
            "currency": currency, "source": "manual",
            "datetime": now_kh().isoformat()
        })
        save_data(data)
        logger.info(f"[MANUAL] {amount} {currency} from {user}")

async def setreport_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[
        InlineKeyboardButton("6:00 AM", callback_data="rpt_6_0"),
        InlineKeyboardButton("8:00 AM", callback_data="rpt_8_0"),
        InlineKeyboardButton("10:00 AM", callback_data="rpt_10_0"),
    ],[
        InlineKeyboardButton("12:00 PM", callback_data="rpt_12_0"),
        InlineKeyboardButton("3:00 PM", callback_data="rpt_15_0"),
        InlineKeyboardButton("5:00 PM", callback_data="rpt_17_0"),
    ],[
        InlineKeyboardButton("7:00 PM", callback_data="rpt_19_0"),
        InlineKeyboardButton("9:00 PM", callback_data="rpt_21_0"),
        InlineKeyboardButton("10:00 PM", callback_data="rpt_22_0"),
    ],[
        InlineKeyboardButton("🚫 Turn OFF", callback_data="rpt_off"),
    ]]
    await update.message.reply_text("🕐 *Set Auto Report Time:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))

async def setreport_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id_int = query.message.chat.id
    chat_id = str(chat_id_int)
    if query.data == "rpt_off":
        for job in context.application.job_queue.get_jobs_by_name(f"report_{chat_id_int}"):
            job.schedule_removal()
        data = load_data()
        chat = get_chat(data, chat_id)
        chat.pop("report_hour", None)
        chat.pop("report_minute", None)
        save_data(data)
        await query.edit_message_text("🚫 *Auto report turned OFF*", parse_mode="Markdown")
        return
    parts = query.data.split("_")
    hour, minute = int(parts[1]), int(parts[2])
    data = load_data()
    chat = get_chat(data, chat_id)
    chat["report_hour"] = hour
    chat["report_minute"] = minute
    save_data(data)
    schedule_report(context.application, chat_id_int, hour, minute)
    await query.edit_message_text(f"✅ *Auto report set at {hour:02d}:{minute:02d}*", parse_mode="Markdown")

async def send_auto_report(context):
    chat_id = context.job.chat_id
    now = now_kh().strftime("%d/%m/%Y")
    text = build_summary(chat_id, "today", f"🌙 Daily Report {now}", "សរុបប្រចាំថ្ងៃ")
    await context.bot.send_message(chat_id=chat_id, text=text + "\n\n✅ រាត្រីល្អ! 🙏", parse_mode="Markdown")

def schedule_report(app, chat_id, hour, minute):
    tz = ZoneInfo(TIMEZONE)
    job_name = f"report_{chat_id}"
    for job in app.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()
    app.job_queue.run_daily(send_auto_report, time=time(hour=hour, minute=minute, tzinfo=tz), chat_id=chat_id, name=job_name)

def restore_schedules(app):
    data = load_data()
    for cid, val in data.items():
        h, m = val.get("report_hour"), val.get("report_minute")
        if h is not None and m is not None:
            try:
                schedule_report(app, int(cid), h, m)
            except:
                pass

# ══════════════════════════════════════════════════════════════════════════════
# MAIN — run both bots together
# ══════════════════════════════════════════════════════════════════════════════
async def run_calculationsbot():
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("help",      start))
    app.add_handler(CommandHandler("today",     today_cmd))
    app.add_handler(CommandHandler("week",      week_cmd))
    app.add_handler(CommandHandler("month",     month_cmd))
    app.add_handler(CommandHandler("total",     total_cmd))
    app.add_handler(CommandHandler("reset",     reset_cmd))
    app.add_handler(CommandHandler("history",   history_cmd))
    app.add_handler(CommandHandler("summary",   summary_cmd))
    app.add_handler(CommandHandler("setreport", setreport_cmd))
    app.add_handler(CallbackQueryHandler(setreport_button, pattern="^rpt_"))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_manual))
    restore_schedules(app)
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=["message", "callback_query"])
    logger.info("🤖 Calculationsbot started!")
    return app

async def main():
    # Start userbot
    if SESSION_STRING:
        await userbot.start()
    else:
        await userbot.start(phone=PHONE)
    logger.info("👁 UserBot started — watching PayWay messages silently")

    # Start calculationsbot
    app = await run_calculationsbot()

    # Run both forever
    try:
        await userbot.run_until_disconnected()
    finally:
        await app.updater.stop()
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    asyncio.run(main())
