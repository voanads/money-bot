#!/usr/bin/env python3
"""
Run this to see RAW updates from Telegram.
Send a PayWay message in your group while this runs.
It will print everything Telegram sends to your bot.
"""
import asyncio
import json
from telegram import Bot

BOT_TOKEN = "8822723106:AAFA2Kkyt8Vikhlegs_d2Li0srrsKrdz7fw"

async def main():
    bot = Bot(token=BOT_TOKEN)
    print("👀 Watching for ALL update types...")
    print("Send a PayWay message in your group now!\n")

    offset = None
    while True:
        updates = await bot.get_updates(
            offset=offset,
            timeout=30,
            allowed_updates=[
                "message",
                "edited_message", 
                "channel_post",
                "edited_channel_post",
                "callback_query",
            ]
        )
        for update in updates:
            offset = update.update_id + 1
            data = update.to_dict()
            print("=" * 60)
            print(f"UPDATE TYPE: {list(data.keys())}")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            print()

asyncio.run(main())
