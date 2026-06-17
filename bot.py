import os
import asyncio
from datetime import datetime
import pytz
import urllib.request
import json
from telegram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
PST = pytz.timezone("America/Los_Angeles")
bot = Bot(token=TELEGRAM_TOKEN)

def get_levels(symbol):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval=5m&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        timestamps = data["chart"]["result"][0]["timestamp"]
        highs = data["chart"]["result"][0]["indicators"]["quote"][0]["high"]
        lows = data["chart"]["result"][0]["indicators"]["quote"][0]["low"]
        pst_times = [datetime.fromtimestamp(t, PST) for t in timestamps]
        for i, t in enumerate(pst_times):
            if t.hour == 6 and t.minute == 20:
                return round(highs[i], 2), round(lows[i], 2)
        # Return latest candle if 6:20 not found
        valid = [(h, l) for h, l in zip(highs, lows) if h and l]
        if valid:
            return round(valid[-1][0], 2), round(valid[-1][1], 2)
        return None, None
    except Exception as e:
        print(f"Error {symbol}: {e}")
        return None, None

async def send_alert():
    now = datetime.now(PST)
    lines = [
        "⏰ *MX Strategy — 6:20 AM Alert*",
        f"📅 {now.strftime('%d %b %Y')} | {now.strftime('%I:%M %p PST')}",
        "─────────────────────────"
    ]
    for name, sym in [("NAS100", "%5ENDXˆ"), ("NAS100", "NQ=F"), ("US30", "YM=F")]:
        pass
    for name, sym in [("NAS100", "NQ=F"), ("US30", "YM=F")]:
        h, l = get_levels(sym)
        if h and l:
            lines += [f"\n📊 *{name}*", f"🟢 High: `{h}`", f"🔴 Low: `{l}`", f"📏 Spread: `{round(h-l,2)}`"]
        else:
            lines += [f"\n📊 *{name}* — ⚠️ Market closed / No data"]
    lines += ["\n─────────────────────────", "⚡ *Enter levels in dashboard NOW*", "🎯 1:4 R/R | Tight SL"]
    await bot.send_message(chat_id=CHAT_ID, text="\n".join(lines), parse_mode="Markdown")

async def handle_updates():
    offset = None
    while True:
        try:
            updates = await bot.get_updates(offset=offset, timeout=10)
            for u in updates:
                offset = u.update_id + 1
                if u.message:
                    txt = u.message.text or ""
                    cid = u.message.chat.id
                    if txt.startswith("/levels"):
                        await bot.send_message(chat_id=cid, text="⏳ Fetching levels...")
                        await send_alert()
                    elif txt.startswith("/status"):
                        now = datetime.now(PST).strftime("%I:%M %p PST")
                        await bot.send_message(chat_id=cid, text=f"✅ Bot running\n🕐 {now}\n⏰ Alert: 6:20 AM PST daily")
                    elif txt.startswith("/start") or txt.startswith("/help"):
                        await bot.send_message(chat_id=cid, text="🤖 *MX Strategy Bot*\n\n/levels — Get levels\n/status — Bot status\n\nAuto alert: *6:20 AM PST* 📡", parse_mode="Markdown")
        except Exception as e:
            print(f"Error: {e}")
        await asyncio.sleep(2)

async def main():
    print("MX Bot starting...")
    scheduler = AsyncIOScheduler(timezone=PST)
    scheduler.add_job(send_alert, "cron", hour=6, minute=20)
    scheduler.start()
    await handle_updates()

if __name__ == "__main__":
    asyncio.run(main())
