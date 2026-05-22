#!/usr/bin/env python3
"""
💰 PayWay ABA Money Tracker Bot
- ONLY need BOT_TOKEN — no GROUP_ID needed!
- One bot works in ALL groups automatically
- Each group has its own separate totals
- Silently saves PayWay ABA messages (no reply)
- Shows totals only when asked: /today /week /month /total /summary
- Sends daily auto report — each group sets its own time via /setreport
"""

import logging
import re
import json
import os
from datetime import datetime, time
from zoneinfo import ZoneInfo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    ContextTypes,
    MessageHandler,
    CommandHandler,
    CallbackQueryHandler,
    filters,
)

# ── ONLY CHANGE THIS ───────────────────────────────────────────────────────────
BOT_TOKEN = "8822723106:AAFA2Kkyt8Vikhlegs_d2Li0srrsKrdz7fw"   # ← Paste your token here, that's all!
# ──────────────────────────────────────────────────────────────────────────────

TIMEZONE  = "Asia/Phnom_Penh"
DATA_FILE = "group_totals.json"

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# ── Data ───────────────────────────────────────────────────────────────────────
def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def get_chat(data: dict, chat_id: str) -> dict:
    if chat_id not in data:
        data[chat_id] = {"history": []}
    if "history" not in data[chat_id]:
        data[chat_id]["history"] = []
    return data[chat_id]

def mark_active(data: dict, chat_id: str):
    """Mark group as active inside an already-loaded data dict (no extra load/save)."""
    get_chat(data, chat_id)
    data[chat_id]["active"] = True

def get_all_active_groups() -> list:
    data = load_data()
    return [cid for cid, val in data.items() if val.get("active")]

def now_kh():
    return datetime.now(ZoneInfo(TIMEZONE))

def fmt_usd(amount: float) -> str:
    return f"${amount:,.2f}"

def fmt_khr(amount) -> str:
    return f"៛{int(amount):,}"

# ── Filter by period ───────────────────────────────────────────────────────────
def filter_history(history, period):
    now = now_kh()
    result = []
    for e in history:
        try:
            dt = datetime.fromisoformat(e["datetime"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=ZoneInfo(TIMEZONE))
            if period == "today":
                if dt.date() == now.date():
                    result.append(e)
            elif period == "week":
                if dt.isocalendar()[:2] == now.isocalendar()[:2]:
                    result.append(e)
            elif period == "month":
                if dt.year == now.year and dt.month == now.month:
                    result.append(e)
            else:
                result.append(e)
        except:
            result.append(e)
    return result

def calc_totals(history):
    usd = 0.0
    khr = 0
    for e in history:
        if e["currency"] == "USD":
            usd += e["amount"]
        else:
            khr += int(e["amount"])
    return usd, khr

# ── Summary builder ────────────────────────────────────────────────────────────
def build_summary(chat_id, period, label_en, label_km):
    data = load_data()
    chat = get_chat(data, str(chat_id))
    history = filter_history(chat["history"], period)
    usd, khr = calc_totals(history)
    count = len(history)
    now = now_kh().strftime("%d/%m/%Y %H:%M")
    return (
        f"📊 *{label_en} / {label_km}*\n"
        f"🕐 {now}\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"💵 USD: `{fmt_usd(usd)}`\n"
        f"💴 KHR: `{fmt_khr(khr)}`\n\n"
        f"📋 Transactions: `{count}`\n"
        f"━━━━━━━━━━━━━━━━"
    )

# ── Parsers ────────────────────────────────────────────────────────────────────
def parse_payway(text):
    # USD: "$12.50 paid by" or "USD 12.50"
    usd = re.search(r"\$\s*(\d+(?:\.\d+)?)\s+(?:paid by|received)", text)
    if not usd:
        usd = re.search(r"(\d+(?:\.\d+)?)\s*USD", text, re.IGNORECASE)
    if usd:
        return float(usd.group(1)), "USD"

    # KHR: "៛136,000 paid by" or "136,000 KHR"
    khr = re.search(r"[៛]\s*(\d[\d,]*)\s+(?:paid by|received)", text)
    if not khr:
        khr = re.search(r"(\d[\d,]*)\s*KHR", text, re.IGNORECASE)
    if khr:
        return int(khr.group(1).replace(",", "")), "KHR"

    # Fallback: any $ amount in the message
    fallback_usd = re.search(r"\$\s*(\d+(?:\.\d+)?)", text)
    if fallback_usd:
        return float(fallback_usd.group(1)), "USD"

    fallback_khr = re.search(r"[៛]\s*(\d[\d,]*)", text)
    if fallback_khr:
        return int(fallback_khr.group(1).replace(",", "")), "KHR"

    return None, None

def parse_amount(text):
    text = text.strip()
    # Symbol before number: $200, ៛200, +50, -25, 55.32
    m = re.match(r"^([+-]?)\s*([៛$]?)\s*(\d[\d,]*(?:\.\d+)?)$", text)
    if m:
        sign_str, sym, num = m.groups()
        sign = -1 if sign_str == "-" else 1
        num = float(num.replace(",", ""))
        if sym == "៛":
            return int(num) * sign, "KHR"
        else:
            return num * sign, "USD"
    # Symbol after number: 200៛, 200$
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

# ── Commands ───────────────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    data = load_data()
    mark_active(data, chat_id)
    save_data(data)
    text = (
        "👋 *PayWay Money Tracker*\n\n"
        "🤫 *Silent mode* — saves all amounts quietly!\n\n"
        "📌 *Saved automatically:*\n"
        "• PayWay ABA messages ✅\n"
        "• `$43` `$25` `+50` `៛136000` ✅\n\n"
        "📋 *Commands:*\n"
        "• `/today` — Today / ថ្ងៃនេះ\n"
        "• `/week` — This week / សប្តាហ៍នេះ\n"
        "• `/month` — This month / ខែនេះ\n"
        "• `/total` — All time / សរុបទាំងអស់\n"
        "• `/summary` — Pick period 📅\n"
        "• `/history` — Last 10 entries\n"
        "• `/reset` — Reset this group\n"
        "• `/setreport` — Set auto report time 🕐\n"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

async def summary_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    mark_active(data, str(update.effective_chat.id))
    save_data(data)
    keyboard = [
        [
            InlineKeyboardButton("📅 Today / ថ្ងៃនេះ",        callback_data="sum_today"),
            InlineKeyboardButton("📆 This Week / សប្តាហ៍នេះ",  callback_data="sum_week"),
        ],
        [
            InlineKeyboardButton("🗓 This Month / ខែនេះ",      callback_data="sum_month"),
            InlineKeyboardButton("📊 All Time / សរុប",         callback_data="sum_all"),
        ],
    ]
    await update.message.reply_text(
        "📅 *Choose period / ជ្រើសរើសរយៈពេល:*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    data_map = {
        "sum_today": ("today", "Today",      "ថ្ងៃនេះ"),
        "sum_week":  ("week",  "This Week",  "សប្តាហ៍នេះ"),
        "sum_month": ("month", "This Month", "ខែនេះ"),
        "sum_all":   ("all",   "All Time",   "សរុបទាំងអស់"),
    }
    period, label_en, label_km = data_map.get(query.data, ("all", "All Time", "សរុប"))
    text = build_summary(chat_id, period, label_en, label_km)
    await query.edit_message_text(text, parse_mode="Markdown")

async def today_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    mark_active(data, str(update.effective_chat.id))
    save_data(data)
    await update.message.reply_text(
        build_summary(update.effective_chat.id, "today", "Today", "ថ្ងៃនេះ"),
        parse_mode="Markdown"
    )

async def week_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    mark_active(data, str(update.effective_chat.id))
    save_data(data)
    await update.message.reply_text(
        build_summary(update.effective_chat.id, "week", "This Week", "សប្តាហ៍នេះ"),
        parse_mode="Markdown"
    )

async def month_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    mark_active(data, str(update.effective_chat.id))
    save_data(data)
    await update.message.reply_text(
        build_summary(update.effective_chat.id, "month", "This Month", "ខែនេះ"),
        parse_mode="Markdown"
    )

async def total_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    mark_active(data, str(update.effective_chat.id))
    save_data(data)
    await update.message.reply_text(
        build_summary(update.effective_chat.id, "all", "All Time Total", "សរុបទាំងអស់"),
        parse_mode="Markdown"
    )

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    chat_id = str(update.effective_chat.id)
    user = update.effective_user.first_name
    data[chat_id] = {"history": [], "active": True}
    save_data(data)
    await update.message.reply_text(
        f"🔄 *Reset by {user}*\n✅ This group data cleared / លុបទិន្នន័យក្រុមនេះ",
        parse_mode="Markdown"
    )

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    chat_id = str(update.effective_chat.id)
    mark_active(data, chat_id)
    save_data(data)
    chat = get_chat(data, chat_id)
    history = chat["history"]

    if not history:
        await update.message.reply_text("📭 No entries yet. / មិនទាន់មានការបញ្ចូលទេ។")
        return

    last_10 = history[-10:]
    lines = []
    for e in reversed(last_10):
        amt = fmt_usd(e["amount"]) if e["currency"] == "USD" else fmt_khr(e["amount"])
        sign = "+" if e["amount"] >= 0 else ""
        dt = e.get("datetime", "")[:16].replace("T", " ")
        lines.append(f"• `{sign}{amt}` — {e['user']} _{e.get('source','manual')}_ `{dt}`")

    usd, khr = calc_totals(history)
    text = (
        f"📋 *Last {len(last_10)} entries:*\n\n"
        + "\n".join(lines)
        + f"\n\n💵 USD Total: `{fmt_usd(usd)}`\n"
        + f"💴 KHR Total: `{fmt_khr(khr)}`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")

# ── Silent message handler ─────────────────────────────────────────────────────
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Handle all message types: normal, forwarded, channel posts, bot messages in group
    message = (
        update.message or
        update.channel_post or
        update.edited_message or
        update.edited_channel_post
    )
    if not message:
        return

    # Grab text from all possible fields (normal, forwarded, caption)
    # Also try forward_origin text for newer Telegram API forwarded messages
    text = message.text or message.caption or ""

    # For forwarded messages from channels (ABA PayWay style), also check forward info
    if not text and hasattr(message, 'forward_origin'):
        try:
            text = message.forward_origin.message.text or ""
        except Exception:
            pass

    text = text.strip()
    if not text:
        return

    data = load_data()
    # Use message.chat.id directly — effective_chat can be None for some channel posts
    chat_id = str(message.chat.id)
    chat = get_chat(data, chat_id)
    mark_active(data, chat_id)

    # Detect sender — bots post without from_user, or from_user.is_bot == True
    if message.from_user:
        if message.from_user.is_bot:
            user = message.from_user.first_name or message.from_user.username or "Bot"
        else:
            user = message.from_user.first_name or "Unknown"
    elif message.sender_chat:
        user = message.sender_chat.title or message.sender_chat.username or "PayWay"
    elif message.via_bot:
        user = message.via_bot.first_name or message.via_bot.username or "PayWay"
    else:
        user = "PayWay"
    dt_now = now_kh().isoformat()

    logger.info(f"[MSG] chat={chat_id} user={user} text={text[:80]!r}")

    # PayWay ABA: detect normal + forwarded messages
    # Covers: "paid by ... Trx. ID", "APV:", KHR/USD variants
    is_payway = (
        ("paid by" in text and "Trx. ID" in text) or
        ("paid by" in text and "APV:" in text) or
        ("paid by" in text and "ABA" in text) or
        ("received" in text.lower() and "Trx. ID" in text) or
        ("Trx. ID" in text and ("$" in text or "៛" in text))
    )
    if is_payway:
        amount, currency = parse_payway(text)
        if amount:
            chat["history"].append({
                "user": user, "amount": amount,
                "currency": currency, "source": "PayWay", "datetime": dt_now
            })
            save_data(data)
            logger.info(f"[SILENT] PayWay {amount} {currency} from '{user}' in chat {chat_id}")
        return

    # Manual amount: $43, +50, ៛136000 — save silently
    amount, currency = parse_amount(text)
    if amount is not None:
        chat["history"].append({
            "user": user, "amount": amount,
            "currency": currency, "source": "manual", "datetime": dt_now
        })
        save_data(data)
        logger.info(f"[SILENT] Manual {amount} {currency} from '{user}' in chat {chat_id}")

# ── /debug command — show raw info of last message ────────────────────────────
async def debug_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Reply to any message with /debug to see its raw fields — helps diagnose PayWay format."""
    msg = update.message
    if not msg.reply_to_message:
        await msg.reply_text(
            "💡 *How to use:*\nReply to a PayWay message with `/debug` to inspect it.",
            parse_mode="Markdown"
        )
        return
    r = msg.reply_to_message
    from_info = ""
    if r.from_user:
        from_info = f"from_user: `{r.from_user.first_name}` is_bot=`{r.from_user.is_bot}`"
    elif r.sender_chat:
        from_info = f"sender_chat: `{r.sender_chat.title}`"
    else:
        from_info = "from: unknown"
    text_preview = (r.text or r.caption or "")[:200]
    is_payway_check = (
        ("paid by" in text_preview and "Trx. ID" in text_preview) or
        ("paid by" in text_preview and "APV:" in text_preview) or
        ("paid by" in text_preview and "ABA" in text_preview) or
        ("received" in text_preview.lower() and "Trx. ID" in text_preview) or
        ("Trx. ID" in text_preview and ("$" in text_preview or "៛" in text_preview))
    )
    amount, currency = parse_payway(text_preview)
    debug_text = (
        f"🔍 *Debug Info*\n"
        f"━━━━━━━━━━━━━━━━\n"
        f"{from_info}\n"
        f"chat type: `{r.chat.type}`\n"
        f"is_payway: `{is_payway_check}`\n"
        f"parsed: `{amount} {currency}`\n\n"
        f"*Text preview:*\n`{text_preview}`"
    )
    await msg.reply_text(debug_text, parse_mode="Markdown")


async def send_auto_report(context):
    chat_id = context.job.chat_id
    now = now_kh().strftime("%d/%m/%Y")
    try:
        text = build_summary(chat_id, "today", f"🌙 Daily Report {now}", "សរុបប្រចាំថ្ងៃ")
        text += "\n\n✅ Have a great night! / រាត្រីល្អ! 🙏"
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        logger.info(f"Auto report sent to {chat_id}")
    except Exception as e:
        logger.warning(f"Could not send report to {chat_id}: {e}")

def schedule_report(app, chat_id: int, hour: int, minute: int):
    """Remove existing job for this group and schedule a new one."""
    tz = ZoneInfo(TIMEZONE)
    job_name = f"report_{chat_id}"
    # Remove old job if exists
    current_jobs = app.job_queue.get_jobs_by_name(job_name)
    for job in current_jobs:
        job.schedule_removal()
    # Schedule new job
    app.job_queue.run_daily(
        send_auto_report,
        time=time(hour=hour, minute=minute, second=0, tzinfo=tz),
        chat_id=chat_id,
        name=job_name,
    )
    logger.info(f"Scheduled report for {chat_id} at {hour:02d}:{minute:02d}")

# ── /setreport command ────────────────────────────────────────────────────────
async def setreport_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    data = load_data()
    mark_active(data, chat_id)
    save_data(data)
    chat_data = data.get(chat_id, {})
    current_hour = chat_data.get("report_hour")
    current_min  = chat_data.get("report_minute")

    if current_hour is not None:
        status = f"⏰ Current: `{current_hour:02d}:{current_min:02d}` (Phnom Penh time)"
    else:
        status = "⏰ No auto report set yet"

    keyboard = [
        [
            InlineKeyboardButton("6:00 AM",  callback_data="rpt_6_0"),
            InlineKeyboardButton("8:00 AM",  callback_data="rpt_8_0"),
            InlineKeyboardButton("10:00 AM", callback_data="rpt_10_0"),
        ],
        [
            InlineKeyboardButton("12:00 PM", callback_data="rpt_12_0"),
            InlineKeyboardButton("3:00 PM",  callback_data="rpt_15_0"),
            InlineKeyboardButton("5:00 PM",  callback_data="rpt_17_0"),
        ],
        [
            InlineKeyboardButton("7:00 PM",  callback_data="rpt_19_0"),
            InlineKeyboardButton("9:00 PM",  callback_data="rpt_21_0"),
            InlineKeyboardButton("10:00 PM", callback_data="rpt_22_0"),
        ],
        [
            InlineKeyboardButton("🚫 Turn OFF auto report", callback_data="rpt_off"),
        ],
    ]
    await update.message.reply_text(
        f"🕐 *Set Auto Report Time*\n{status}\n\n"
        f"Choose what time to send daily summary:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def setreport_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    chat_id_int = query.message.chat.id
    chat_id = str(chat_id_int)

    if query.data == "rpt_off":
        # Remove scheduled job
        job_name = f"report_{chat_id_int}"
        for job in context.application.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
        # Save setting
        data = load_data()
        chat = get_chat(data, chat_id)
        chat.pop("report_hour", None)
        chat.pop("report_minute", None)
        save_data(data)
        await query.edit_message_text(
            "🚫 *Auto report turned OFF*\n\nUse /setreport to turn it back on.",
            parse_mode="Markdown"
        )
        return

    # Parse rpt_HH_MM
    parts = query.data.split("_")
    hour   = int(parts[1])
    minute = int(parts[2])

    # Save to data
    data = load_data()
    chat = get_chat(data, chat_id)
    chat["report_hour"]   = hour
    chat["report_minute"] = minute
    save_data(data)

    # Schedule the job
    schedule_report(context.application, chat_id_int, hour, minute)

    label = f"{hour:02d}:{minute:02d}"
    await query.edit_message_text(
        f"✅ *Auto report set!*\n\n"
        f"📅 Every day at `{label}` (Phnom Penh time)\n"
        f"I will send today\'s summary automatically.\n\n"
        f"Use /setreport to change or turn off.",
        parse_mode="Markdown"
    )

# ── Restore scheduled reports on startup ──────────────────────────────────────
def restore_schedules(app):
    data = load_data()
    count = 0
    for chat_id_str, val in data.items():
        h = val.get("report_hour")
        m = val.get("report_minute")
        if h is not None and m is not None:
            try:
                schedule_report(app, int(chat_id_str), h, m)
                count += 1
            except Exception as e:
                logger.warning(f"Could not restore schedule for {chat_id_str}: {e}")
    if count:
        logger.info(f"Restored {count} scheduled report(s)")

# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("help",      start))
    app.add_handler(CommandHandler("debug",     debug_command))
    app.add_handler(CommandHandler("summary",   summary_command))
    app.add_handler(CommandHandler("today",     today_command))
    app.add_handler(CommandHandler("week",      week_command))
    app.add_handler(CommandHandler("month",     month_command))
    app.add_handler(CommandHandler("total",     total_command))
    app.add_handler(CommandHandler("reset",     reset_command))
    app.add_handler(CommandHandler("history",   history_command))
    app.add_handler(CommandHandler("setreport", setreport_command))
    app.add_handler(CallbackQueryHandler(setreport_button, pattern="^rpt_"))
    app.add_handler(CallbackQueryHandler(button_handler))
    # Catch regular user messages
    app.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        handle_message
    ))
    # KEY FIX: PayWay by ABA posts as a channel inside the group (sender_chat)
    # These are NOT caught by filters.TEXT — need filters.SenderChat.ALL
    app.add_handler(MessageHandler(
        filters.SenderChat.ALL,
        handle_message
    ))
    # Also catch pure channel_post updates
    app.add_handler(MessageHandler(
        filters.UpdateType.CHANNEL_POSTS,
        handle_message
    ))

    # Restore any saved report schedules from previous run
    restore_schedules(app)

    logger.info("🤖 Bot running — works in ALL groups automatically!")
    logger.info("🔍 Debug: listening for bot/channel messages (ABA PayWay mode ON)")
    app.run_polling(allowed_updates=[
        "message",
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "callback_query",
    ])

if __name__ == "__main__":
    main()
