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

# RSI alert already sent flags
rsi_alert_sent = {"15m": False, "1h": False}

def fetch_ohlc(symbol, interval):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range=5d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        return closes
    except Exception as e:
        print(f"Error fetching {symbol} {interval}: {e}")
        return []

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)

def get_gold_price():
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/GC=F?interval=1m&range=1d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        closes = [c for c in closes if c is not None]
        return round(closes[-1], 2) if closes else None
    except:
        return None

async def check_gold_rsi():
    global rsi_alert_sent
    now = datetime.now(PST)

    for tf, interval, label in [("15m", "15m", "15 Min"), ("1h", "1h", "1 Hour")]:
        closes = fetch_ohlc("GC=F", interval)
        rsi = calc_rsi(closes)
        price = get_gold_price()

        if rsi is None:
            continue

        print(f"Gold RSI {label}: {rsi}")

        # RSI 30 or below — BUY zone
        if rsi <= 35 and not rsi_alert_sent[tf]:
            rsi_alert_sent[tf] = True
            msg = (
                f"🚨 *GOLD RSI ALERT — {label}*\n"
                f"📅 {now.strftime('%d %b %Y | %I:%M %p PST')}\n"
                f"─────────────────────────\n"
                f"💰 Gold Price: `${price}`\n"
                f"📊 RSI ({label}): `{rsi}`\n\n"
                f"{'🟢 RSI at 30 — Strong BUY zone!' if rsi <= 30 else '🟡 RSI at 35 — Approaching BUY zone'}\n\n"
                f"⚡ *Watch for reversal signal*\n"
                f"🎯 Enter on confirmation | 1:3 R/R\n"
                f"🛡️ SL below recent low"
            )
            await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")

        # Reset flag when RSI goes above 50
        elif rsi > 50:
            rsi_alert_sent[tf] = False

async def send_gold_status(cid):
    lines = ["📊 *Gold RSI Status*\n"]
    price = get_gold_price()
    if price:
        lines.append(f"💰 Current Price: `${price}`\n")

    for tf, interval, label in [("15m", "15m", "15 Min"), ("1h", "1h", "1 Hour")]:
        closes = fetch_ohlc("GC=F", interval)
        rsi = calc_rsi(closes)
        if rsi:
            if rsi <= 30:
                emoji = "🟢"
                zone = "STRONG BUY"
            elif rsi <= 35:
                emoji = "🟡"
                zone = "Watch Zone"
            elif rsi >= 70:
                emoji = "🔴"
                zone = "OVERBOUGHT"
            else:
                emoji = "⚪"
                zone = "Neutral"
            lines.append(f"{emoji} RSI {label}: `{rsi}` — {zone}")
        else:
            lines.append(f"⚠️ RSI {label}: Data unavailable")

    await bot.send_message(chat_id=cid, text="\n".join(lines), parse_mode="Markdown")

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
    for name, sym in [("NAS100", "NQ=F"), ("US30", "YM=F")]:
        h, l = get_levels(sym)
        if h and l:
            lines += [f"\n📊 *{name}*", f"🟢 High: `{h}`", f"🔴 Low: `{l}`", f"📏 Spread: `{round(h-l,2)}`"]
        else:
            lines += [f"\n📊 *{name}* — ⚠️ Market closed"]
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
                    elif txt.startswith("/gold"):
                        await send_gold_status(cid)
                    elif txt.startswith("/status"):
                        now = datetime.now(PST).strftime("%I:%M %p PST")
                        await bot.send_message(chat_id=cid, text=f"✅ Bot running\n🕐 {now}\n⏰ MX Alert: 6:20 AM PST\n📊 Gold RSI: Checking every 15 mins")
                    elif txt.startswith("/start") or txt.startswith("/help"):
                        await bot.send_message(chat_id=cid, text="🤖 *MX Strategy Bot*\n\n/levels — NAS100 & US30 levels\n/gold — Gold RSI status\n/status — Bot status\n\nAuto alerts:\n⏰ MX: 6:20 AM PST\n🥇 Gold RSI: Auto when RSI ≤ 35", parse_mode="Markdown")
        except Exception as e:
            print(f"Error: {e}")
        await asyncio.sleep(2)

async def main():
    print("MX Bot starting...")
    scheduler = AsyncIOScheduler(timezone=PST)
    scheduler.add_job(send_alert, "cron", hour=6, minute=20)
    scheduler.add_job(check_gold_rsi, "interval", minutes=15)
    scheduler.start()
    await handle_updates()

if __name__ == "__main__":
    asyncio.run(main())
