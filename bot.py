import os
import asyncio
from datetime import datetime
import pytz
import yfinance as yf
from telegram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID        = os.environ.get("CHAT_ID")

PST = pytz.timezone("America/Los_Angeles")

ASSETS = {
    "NAS100": "NQ=F",
    "US30":   "YM=F",
}

bot = Bot(token=TELEGRAM_TOKEN)

def get_620_levels(ticker_symbol):
    try:
        ticker = yf.Ticker(ticker_symbol)
        df = ticker.history(period="1d", interval="5m")
        if df.empty:
            return None, None
        df.index = df.index.tz_convert(PST)
        for idx, row in df.iterrows():
            if idx.hour == 6 and idx.minute == 20:
                return round(row['High'], 2), round(row['Low'], 2)
        last = df.iloc[-1]
        return round(last['High'], 2), round(last['Low'], 2)
    except Exception as e:
        print(f"Error: {e}")
        return None, None

async def send_620_alert():
    now_pst  = datetime.now(PST)
    date_str = now_pst.strftime("%d %b %Y")
    time_str = now_pst.strftime("%I:%M %p PST")
    lines = ["⏰ *MX Strategy — 6:20 AM Alert*", f"📅 {date_str} | {time_str}", "─────────────────────────"]
    for name, symbol in ASSETS.items():
        high, low = get_620_levels(symbol)
        if high and low:
            lines += [f"\n📊 *{name}*", f"🟢 Resistance: `{high}`", f"🔴 Support:    `{low}`", f"📏 Spread: `{round(high-low,2)}`"]
        else:
            lines.append(f"\n📊 *{name}* — ⚠️ Data unavailable")
    lines += ["\n─────────────────────────", "⚡ *Enter levels in dashboard NOW*", "🎯 Wait for breakout | 1:4 R/R"]
    await bot.send_message(chat_id=CHAT_ID, text="\n".join(lines), parse_mode="Markdown")

async def send_startup():
    await bot.send_message(chat_id=CHAT_ID, text="✅ *MX Strategy Bot is LIVE!*\n\nAuto alert: *6:20 AM PST daily*\n\n/levels — Get levels now\n/status — Bot status", parse_mode="Markdown")

async def handle_updates():
    offset = None
    while True:
        try:
            updates = await bot.get_updates(offset=offset, timeout=10)
            for update in updates:
                offset = update.update_id + 1
                if update.message:
                    text = update.message.text or ""
                    cid  = update.message.chat.id
                    if text.startswith("/levels"):
                        await bot.send_message(chat_id=cid, text="⏳ Fetching levels...")
                        await send_620_alert()
                    elif text.startswith("/status"):
                        now = datetime.now(PST).strftime("%I:%M %p PST")
                        await bot.send_message(chat_id=cid, text=f"✅ Bot running\n🕐 {now}\n⏰ Next alert: 6:20 AM PST")
                    elif text.startswith("/start") or text.startswith("/help"):
                        await bot.send_message(chat_id=cid, text="🤖 *MX Strategy Bot*\n\n/levels — NAS100 & US30 levels\n/status — Bot status\n\nAuto alert: *6:20 AM PST* 📡", parse_mode="Markdown")
        except Exception as e:
            print(f"Update error: {e}")
        await asyncio.sleep(2)

async def main():
    print("MX Bot starting...")

    scheduler = AsyncIOScheduler(timezone=PST)
    scheduler.add_job(send_620_alert, "cron", hour=6, minute=20)
    scheduler.start()
    await handle_updates()

if __name__ == "__main__":
    asyncio.run(main())
