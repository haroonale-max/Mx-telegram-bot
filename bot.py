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

rsi_alert_sent = {"15m": False, "1h": False}
macd_alert_sent = {"15m": False, "1h": False}

def fetch_closes(symbol, interval):
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?interval={interval}&range=5d"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read())
        closes = data["chart"]["result"][0]["indicators"]["quote"][0]["close"]
        return [c for c in closes if c is not None]
    except Exception as e:
        print(f"Error {symbol} {interval}: {e}")
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
    return round(100 - (100 / (1 + avg_gain / avg_loss)), 2)

def calc_ema(closes, period):
    if len(closes) < period:
        return []
    k = 2 / (period + 1)
    ema = [sum(closes[:period]) / period]
    for price in closes[period:]:
        ema.append(price * k + ema[-1] * (1 - k))
    return ema

def calc_macd(closes):
    if len(closes) < 35:
        return None, None, None
    ema12 = calc_ema(closes, 12)
    ema26 = calc_ema(closes, 26)
    min_len = min(len(ema12), len(ema26))
    macd_line = [ema12[-(min_len-i)] - ema26[-(min_len-i)] for i in range(min_len)]
    if len(macd_line) < 9:
        return None, None, None
    signal = calc_ema(macd_line, 9)
    if not signal:
        return None, None, None
    macd_val = round(macd_line[-1], 4)
    signal_val = round(signal[-1], 4)
    hist = round(macd_val - signal_val, 4)
    return macd_val, signal_val, hist

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

async def check_gold_signals():
    global rsi_alert_sent, macd_alert_sent
    now = datetime.now(PST)
    price = get_gold_price()

    for tf, interval, label in [("15m", "15m", "15 Min"), ("1h", "1h", "1 Hour")]:
        closes = fetch_closes("GC=F", interval)
        rsi = calc_rsi(closes)
        macd, signal, hist = calc_macd(closes)

        if rsi is None or macd is None:
            continue

        print(f"Gold {label} — RSI: {rsi} | MACD: {macd} | Signal: {signal} | Hist: {hist}")

        # --- RSI Alert ---
        if rsi <= 35 and not rsi_alert_sent[tf]:
            rsi_zone = "🟢 STRONG BUY ZONE" if rsi <= 30 else "🟡 Watch Zone"
            macd_status = "✅ MACD Bullish Cross!" if hist and hist > 0 else "⚠️ MACD not confirmed yet"
            confluence = "🔥 HIGH CONFLUENCE SIGNAL!" if (rsi <= 35 and hist and hist > 0) else "⏳ Wait for MACD confirmation"

            msg = (
                f"🚨 *GOLD RSI ALERT — {label}*\n"
                f"📅 {now.strftime('%d %b %Y | %I:%M %p PST')}\n"
                f"─────────────────────────\n"
                f"💰 Price: `${price}`\n\n"
                f"📊 *RSI ({label}):* `{rsi}` — {rsi_zone}\n"
                f"📈 *MACD:* `{macd}` | Signal: `{signal}`\n"
                f"📉 *Histogram:* `{hist}` — {macd_status}\n\n"
                f"{'─' * 25}\n"
                f"{confluence}\n\n"
                f"✅ Check support levels on TradingView\n"
                f"📰 Check news on Forex Factory\n"
                f"🎯 If confirmed: Enter | 1:3 R/R | Tight SL"
            )
            await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")
            rsi_alert_sent[tf] = True

        elif rsi > 50:
            rsi_alert_sent[tf] = False

        # --- MACD Bullish Cross Alert (even if RSI not at 35) ---
        if hist and hist > 0 and not macd_alert_sent[tf]:
            if rsi and rsi < 50:  # Only alert if RSI shows some weakness
                macd_alert_sent[tf] = True
                msg = (
                    f"📈 *GOLD MACD CROSS — {label}*\n"
                    f"📅 {now.strftime('%d %b %Y | %I:%M %p PST')}\n"
                    f"─────────────────────────\n"
                    f"💰 Price: `${price}`\n\n"
                    f"✅ MACD crossed above Signal!\n"
                    f"📊 MACD: `{macd}` | Signal: `{signal}`\n"
                    f"📉 Histogram: `{hist}`\n"
                    f"🔵 RSI: `{rsi}`\n\n"
                    f"⚡ Potential bullish momentum building\n"
                    f"🎯 Watch for entry if RSI < 50 & support holds"
                )
                await bot.send_message(chat_id=CHAT_ID, text=msg, parse_mode="Markdown")

        elif hist and hist < 0:
            macd_alert_sent[tf] = False

async def send_gold_status(cid):
    price = get_gold_price()
    lines = ["📊 *Gold Full Analysis*\n"]
    if price:
        lines.append(f"💰 Price: `${price}`\n")

    for tf, interval, label in [("15m", "15m", "15 Min"), ("1h", "1h", "1 Hour")]:
        closes = fetch_closes("GC=F", interval)
        rsi = calc_rsi(closes)
        macd, signal, hist = calc_macd(closes)

        lines.append(f"─── *{label}* ───")

        if rsi:
            if rsi <= 30: emoji, zone = "🟢", "STRONG BUY"
            elif rsi <= 35: emoji, zone = "🟡", "Watch Zone"
            elif rsi >= 70: emoji, zone = "🔴", "OVERBOUGHT"
            else: emoji, zone = "⚪", "Neutral"
            lines.append(f"{emoji} RSI: `{rsi}` — {zone}")
        else:
            lines.append("⚠️ RSI: N/A")

        if macd and signal and hist:
            macd_emoji = "📈" if hist > 0 else "📉"
            macd_trend = "Bullish" if hist > 0 else "Bearish"
            lines.append(f"{macd_emoji} MACD: `{macd}` | Sig: `{signal}`")
            lines.append(f"   Histogram: `{hist}` — {macd_trend}\n")
        else:
            lines.append("⚠️ MACD: N/A\n")

    lines.append("─────────────────────────")
    lines.append("📰 News: forex factory.com")
    lines.append("📊 Support: Check TradingView")

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

async def send_mx_alert():
    now = datetime.now(PST)
    lines = ["⏰ *MX Strategy — 6:20 AM Alert*", f"📅 {now.strftime('%d %b %Y')} | {now.strftime('%I:%M %p PST')}", "─────────────────────────"]
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
                        await send_mx_alert()
                    elif txt.startswith("/gold"):
                        await send_gold_status(cid)
                    elif txt.startswith("/status"):
                        now = datetime.now(PST).strftime("%I:%M %p PST")
                        await bot.send_message(chat_id=cid, text=f"✅ Bot running\n🕐 {now}\n⏰ MX Alert: 6:20 AM PST\n📊 Gold RSI+MACD: Every 15 mins\n\nCommands:\n/levels /gold /status", parse_mode="Markdown")
                    elif txt.startswith("/start") or txt.startswith("/help"):
                        await bot.send_message(chat_id=cid, text="🤖 *MX Strategy Bot*\n\n/levels — NAS100 & US30 levels\n/gold — Gold RSI + MACD analysis\n/status — Bot status\n\nAuto alerts:\n⏰ MX: 6:20 AM PST daily\n🥇 Gold RSI ≤ 35 → Alert\n📈 Gold MACD Cross → Alert", parse_mode="Markdown")
        except Exception as e:
            print(f"Error: {e}")
        await asyncio.sleep(2)

async def main():
    print("MX Bot starting...")
    scheduler = AsyncIOScheduler(timezone=PST)
    scheduler.add_job(send_mx_alert, "cron", hour=6, minute=20)
    scheduler.add_job(check_gold_signals, "interval", minutes=15)
    scheduler.start()
    await handle_updates()

if __name__ == "__main__":
    asyncio.run(main())
