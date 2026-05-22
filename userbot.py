#!/usr/bin/env python3
"""
💰 PayWay ABA Money Tracker — UserBot (Telethon)
Runs as a real Telegram user account — can see ALL messages including PayWay bot
"""

import re
import json
import os
import logging
from datetime import datetime
from zoneinfo import ZoneInfo
from telethon import TelegramClient, events
from telethon.tl.types import PeerChannel, PeerChat, PeerUser

# ── CHANGE THESE ──────────────────────────────────────────────────────────────
API_ID      = 36474508
API_HASH    = "86a53c87962052aca9e4a28f7aa327d8"
PHONE       = "+85511205275"   # ← ใส่ phone number ជាមួយ country code (ឧ. +85512345678)
BOT_TOKEN   = "8822723106:AAFA2Kkyt8Vikhlegs_d2Li0srrsKrdz7fw"  # Bot token សម្រាប់ reply commands
# ─────────────────────────────────────────────────────────────────────────────

TIMEZONE  = "Asia/Phnom_Penh"
DATA_FILE = "group_totals.json"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# ── Data helpers ──────────────────────────────────────────────────────────────
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

# ── PayWay parser ─────────────────────────────────────────────────────────────
def parse_payway(text):
    # USD
    usd = re.search(r"\$\s*(\d+(?:\.\d+)?)", text)
    if usd:
        return float(usd.group(1)), "USD"
    # KHR
    khr = re.search(r"[៛]\s*(\d[\d,]*)", text)
    if khr:
        return int(khr.group(1).replace(",", "")), "KHR"
    return None, None

def is_payway_message(text):
    return (
        ("paid by" in text and "Trx. ID" in text) or
        ("paid by" in text and "APV:" in text) or
        ("paid by" in text and "ABA" in text) or
        ("Trx. ID" in text and ("$" in text or "៛" in text))
    )

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
        f"📊 **{label_en} / {label_km}**\n"
        f"🕐 {now}\n"
        f"━━━━━━━━━━━━━━━━\n\n"
        f"💵 USD: `{fmt_usd(usd)}`\n"
        f"💴 KHR: `{fmt_khr(khr)}`\n\n"
        f"📋 Transactions: `{len(history)}`\n"
        f"━━━━━━━━━━━━━━━━"
    )

# ── Main ──────────────────────────────────────────────────────────────────────
client = TelegramClient("userbot_session", API_ID, API_HASH)

@client.on(events.NewMessage())
async def handler(event):
    text = event.raw_text or ""
    chat_id = event.chat_id
    sender = await event.get_sender()
    sender_name = getattr(sender, "first_name", None) or getattr(sender, "title", None) or "Unknown"

    # ── Detect PayWay message ──
    if is_payway_message(text):
        amount, currency = parse_payway(text)
        if amount:
            data = load_data()
            chat = get_chat(data, chat_id)
            chat["history"].append({
                "user": sender_name,
                "amount": amount,
                "currency": currency,
                "source": "PayWay",
                "datetime": now_kh().isoformat()
            })
            save_data(data)
            logger.info(f"✅ PayWay {amount} {currency} from '{sender_name}' in chat {chat_id}")
        return

    # ── Commands ──
    if text.strip() == "/today":
        await event.reply(build_summary(chat_id, "today", "Today", "ថ្ងៃនេះ"))
    elif text.strip() == "/week":
        await event.reply(build_summary(chat_id, "week", "This Week", "សប្តាហ៍នេះ"))
    elif text.strip() == "/month":
        await event.reply(build_summary(chat_id, "month", "This Month", "ខែនេះ"))
    elif text.strip() == "/total":
        await event.reply(build_summary(chat_id, "all", "All Time", "សរុបទាំងអស់"))
    elif text.strip() == "/reset":
        data = load_data()
        data[str(chat_id)] = {"history": []}
        save_data(data)
        await event.reply("🔄 Reset done!")

async def main():
    await client.start(phone=PHONE)
    logger.info("🤖 UserBot started — watching ALL messages including PayWay!")
    await client.run_until_disconnected()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
