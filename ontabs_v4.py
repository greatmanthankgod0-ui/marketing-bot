import os
import random
import sqlite3
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# ─────────────────────────────────────────
#  CONFIG — replace with your real values
# ─────────────────────────────────────────
TOKEN    = "YOUR_TOKEN_HERE"
ADMIN_ID = 123456789

ESCROW_BANK    = "GTBank"
ESCROW_NAME    = "OnTabs Business Inc"
ESCROW_ACCOUNT = "0123456789"
ONTABS_FEE_PCT = 0.005  # 0.5%

bot = telebot.TeleBot(TOKEN)
DB  = "ontabs_v4.db"

# ─────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS sellers (
        seller_id    INTEGER PRIMARY KEY,
        shop_name    TEXT,
        bank_name    TEXT,
        account_no   TEXT,
        account_name TEXT,
        delivery_hrs INTEGER DEFAULT 24,
        is_approved  INTEGER DEFAULT 0,
        joined_at    TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER,
        category  TEXT,
        color     TEXT,
        price     REAL,
        stock     INTEGER DEFAULT -1,
        gender    TEXT DEFAULT 'Unisex'
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS buyer_sessions (
        user_id            INTEGER PRIMARY KEY,
        state              TEXT,
        current_category   TEXT,
        current_seller_id  INTEGER,
        gender_pref        TEXT,
        pending_product_id INTEGER,
        quantity           INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS seller_sessions (
        seller_id    INTEGER PRIMARY KEY,
        state        TEXT,
        shop_name    TEXT,
        bank_name    TEXT,
        account_no   TEXT,
        account_name TEXT,
        delivery_hrs INTEGER
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        reference       TEXT UNIQUE,
        buyer_id        INTEGER,
        seller_id       INTEGER,
        product_id      INTEGER,
        buyer_name      TEXT,
        item_desc       TEXT,
        quantity        INTEGER,
        unit_price      REAL,
        gross_amount    REAL,
        ontabs_fee      REAL,
        seller_receives REAL,
        status          TEXT DEFAULT 'AWAITING_PAYMENT',
        frozen          INTEGER DEFAULT 1,
        created_at      TEXT,
        paid_at         TEXT,
        release_at      TEXT,
        released_at     TEXT
    )''')

    conn.commit()
    conn.close()

def get_conn():
    return sqlite3.connect(DB)

# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────
def gen_reference():
    conn = get_conn()
    c = conn.cursor()
    while True:
        ref = f"OT-{''.join([str(random.randint(0,9)) for _ in range(9)])}"
        c.execute("SELECT id FROM orders WHERE reference = ?", (ref,))
        if not c.fetchone():
            conn.close()
            return ref

def gender_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row(KeyboardButton("👗 For a Lady"), KeyboardButton("👔 For a Man"))
    kb.row(KeyboardButton("🎁 It's a Gift"))
    return kb

def is_seller(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT seller_id FROM sellers WHERE seller_id = ? AND is_approved = 1", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def is_pending_seller(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT state FROM seller_sessions WHERE seller_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result is not None

def get_seller_session(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT state, shop_name, bank_name, account_no, account_name, delivery_hrs FROM seller_sessions WHERE seller_id = ?", (user_id,))
    result = c.fetchone()
    conn.close()
    return result

def get_session(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT state, current_category, gender_pref,
                 pending_product_id, quantity, current_seller_id
                 FROM buyer_sessions WHERE user_id = ?""", (user_id,))
    result = c.fetchone()
    conn.close()
    return result
    # [0]state [1]category [2]gender [3]product_id [4]qty [5]seller_id

def get_colors(category, gender, seller_id=None):
    conn = get_conn()
    c = conn.cursor()
    if seller_id:
        c.execute("""SELECT color, price, stock FROM products
                     WHERE seller_id = ? AND category = ?
                     AND (gender = ? OR gender = 'Unisex') COLLATE NOCASE
                     ORDER BY color""", (seller_id, category, gender))
    else:
        c.execute("""SELECT color, price, stock FROM products
                     WHERE category = ?
                     AND (gender = ? OR gender = 'Unisex') COLLATE NOCASE
                     ORDER BY color""", (category, gender))
    rows = c.fetchall()
    conn.close()
    return rows

def format_colors(rows):
    if not rows:
        return None
    lines = []
    for color, price, stock in rows:
        stock_label = f"{stock} yds" if stock >= 0 else "In Stock"
        lines.append(f"🔹 {color} — ₦{price:,} ({stock_label})")
    return "\n".join(lines)

def get_shop_list():
    """Returns approved shops that have at least one product."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT s.seller_id, s.shop_name,
                        GROUP_CONCAT(DISTINCT p.category) as cats,
                        COUNT(p.id) as cnt
                 FROM sellers s
                 JOIN products p ON s.seller_id = p.seller_id
                 WHERE s.is_approved = 1
                 GROUP BY s.seller_id
                 ORDER BY s.shop_name""")
    rows = c.fetchall()
    conn.close()
    return rows

# ─────────────────────────────────────────
#  /start
# ─────────────────────────────────────────
@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.chat.id
    name    = message.from_user.first_name

    if user_id == ADMIN_ID:
        bot.reply_to(message,
            "👑 *Welcome back, Boss!*\n\n"
            "/approve [id] — Approve seller\n"
            "/freeze [ref] — Freeze order\n"
            "/release [ref] — Release funds\n"
            "/orders — All orders\n"
            "/sellers — All sellers",
            parse_mode="Markdown"
        )
        return

    if is_seller(user_id):
        seller_dashboard(message)
        return

    if is_pending_seller(user_id):
        bot.reply_to(message, "👋 You're still registering your shop! Let's continue 😊")
        handle_seller_reg(message)
        return

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row(KeyboardButton("🛍️ I want to buy"), KeyboardButton("🏪 I want to sell"))
    bot.reply_to(message,
        f"Hey *{name}!* 👋\n\n"
        f"Welcome to *OnTabs* — Nigeria's most trusted marketplace 🇳🇬\n\n"
        f"What brings you here today?",
        reply_markup=kb,
        parse_mode="Markdown"
    )

# ─────────────────────────────────────────
#  SELLER DASHBOARD
# ─────────────────────────────────────────
def seller_dashboard(message):
    user_id = message.chat.id
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT shop_name FROM sellers WHERE seller_id = ?", (user_id,))
    seller = c.fetchone()
    c.execute("SELECT COUNT(*) FROM orders WHERE seller_id = ? AND status = 'AWAITING_PAYMENT'", (user_id,))
    pending = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM orders WHERE seller_id = ? AND status = 'PAID' AND frozen = 1", (user_id,))
    frozen = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(seller_receives),0) FROM orders WHERE seller_id = ? AND status = 'RELEASED'", (user_id,))
    earned = c.fetchone()[0]
    conn.close()

    bot.send_message(user_id,
        f"👋 Welcome back, *{seller[0]}!*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔴 Awaiting Payment: *{pending}*\n"
        f"🟡 In Escrow: *{frozen}*\n"
        f"✅ Total Released: *₦{earned:,.0f}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"/addproduct — Add item\n"
        f"/mystock — View catalog\n"
        f"/myorders — View orders",
        parse_mode="Markdown"
    )

# ─────────────────────────────────────────
#  SELLER REGISTRATION
# ─────────────────────────────────────────
def start_seller_reg(message):
    user_id = message.chat.id
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO seller_sessions (seller_id, state) VALUES (?, 'ASK_SHOP_NAME')", (user_id,))
    conn.commit()
    conn.close()
    bot.send_message(user_id,
        "🏪 *Let's set up your OnTabs shop!*\n\nWhat's the name of your shop? 👇",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

def handle_seller_reg(message):
    user_id = message.chat.id
    text    = message.text.strip()
    sess    = get_seller_session(user_id)
    if not sess:
        return
    state = sess[0]
    conn = get_conn()
    c = conn.cursor()

    if state == "ASK_SHOP_NAME":
        c.execute("UPDATE seller_sessions SET shop_name = ?, state = 'ASK_BANK_NAME' WHERE seller_id = ?", (text, user_id))
        conn.commit()
        conn.close()
        bot.send_message(user_id, f"Love it! *{text}* 🔥\n\nWhich bank will you receive payments to?\n_(e.g. GTBank, Opay, Palmpay)_", parse_mode="Markdown")

    elif state == "ASK_BANK_NAME":
        c.execute("UPDATE seller_sessions SET bank_name = ?, state = 'ASK_ACCOUNT_NO' WHERE seller_id = ?", (text, user_id))
        conn.commit()
        conn.close()
        bot.send_message(user_id, f"Got it — *{text}* ✅\n\nWhat's your account number? 👇", parse_mode="Markdown")

    elif state == "ASK_ACCOUNT_NO":
        if not text.isdigit() or len(text) < 10:
            conn.close()
            bot.send_message(user_id, "⚠️ Please enter a valid 10-digit account number.")
            return
        c.execute("UPDATE seller_sessions SET account_no = ?, state = 'ASK_ACCOUNT_NAME' WHERE seller_id = ?", (text, user_id))
        conn.commit()
        conn.close()
        bot.send_message(user_id, "Perfect! 👌\n\nWhat's the account name?", parse_mode="Markdown")

    elif state == "ASK_ACCOUNT_NAME":
        c.execute("UPDATE seller_sessions SET account_name = ?, state = 'ASK_DELIVERY_HRS' WHERE seller_id = ?", (text, user_id))
        conn.commit()
        conn.close()
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.row(KeyboardButton("6 hours"), KeyboardButton("12 hours"))
        kb.row(KeyboardButton("24 hours"), KeyboardButton("48 hours"))
        bot.send_message(user_id,
            "Almost done! 🎉\n\nHow long does it take for orders to reach the buyer?\n_(This sets the escrow release timer)_",
            reply_markup=kb
        )

    elif state == "ASK_DELIVERY_HRS":
        hrs_map = {"6 hours": 6, "12 hours": 12, "24 hours": 24, "48 hours": 48}
        hrs = hrs_map.get(text)
        if not hrs:
            conn.close()
            bot.send_message(user_id, "Please pick one of the options 👆")
            return
        c.execute("SELECT shop_name, bank_name, account_no, account_name FROM seller_sessions WHERE seller_id = ?", (user_id,))
        s = c.fetchone()
        c.execute("""INSERT OR REPLACE INTO sellers
                     (seller_id, shop_name, bank_name, account_no, account_name, delivery_hrs, is_approved, joined_at)
                     VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
                  (user_id, s[0], s[1], s[2], s[3], hrs, datetime.now().isoformat()))
        c.execute("DELETE FROM seller_sessions WHERE seller_id = ?", (user_id,))
        conn.commit()
        conn.close()
        bot.send_message(user_id,
            f"🎊 *Application Submitted!*\n\nShop: *{s[0]}*\nBank: {s[1]} — {s[2]}\nDelivery: {hrs}hrs\n\nWaiting for OnTabs approval! 🚀",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )
        bot.send_message(ADMIN_ID,
            f"🏪 *NEW SELLER*\n\nName: {message.from_user.first_name}\nID: `{user_id}`\nShop: *{s[0]}*\nBank: {s[1]} — {s[2]}\nAccount: {s[3]}\nDelivery: {hrs}hrs\n\n/approve {user_id}",
            parse_mode="Markdown"
        )

# ─────────────────────────────────────────
#  ADMIN COMMANDS
# ─────────────────────────────────────────
@bot.message_handler(commands=['approve'])
def cmd_approve(message):
    if message.chat.id != ADMIN_ID: return
    try:
        seller_id = int(message.text.split()[1])
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE sellers SET is_approved = 1 WHERE seller_id = ?", (seller_id,))
        conn.commit()
        c.execute("SELECT shop_name FROM sellers WHERE seller_id = ?", (seller_id,))
        shop = c.fetchone()
        conn.close()
        bot.reply_to(message, f"✅ *{shop[0]}* is now LIVE!", parse_mode="Markdown")
        bot.send_message(seller_id,
            f"🎉 *Your shop is LIVE on OnTabs!*\n\nStart with /addproduct\nSee your dashboard with /start 🚀",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message, f"Usage: /approve [seller_id]\nError: {e}")

@bot.message_handler(commands=['release'])
def cmd_release(message):
    if message.chat.id != ADMIN_ID: return
    try:
        ref = message.text.split()[1].upper()
        conn = get_conn()
        c = conn.cursor()
        c.execute("""SELECT o.seller_id, o.seller_receives, o.buyer_id, o.item_desc,
                            s.shop_name, s.bank_name, s.account_no, s.account_name
                     FROM orders o JOIN sellers s ON o.seller_id = s.seller_id
                     WHERE o.reference = ?""", (ref,))
        order = c.fetchone()
        if not order:
            conn.close()
            bot.reply_to(message, f"❌ Order {ref} not found.")
            return
        c.execute("UPDATE orders SET frozen = 0, status = 'RELEASED', released_at = ? WHERE reference = ?",
                  (datetime.now().isoformat(), ref))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ *Funds Released!*\nRef: `{ref}`\nAmount: ₦{order[1]:,.0f}\nTo: {order[5]} — {order[6]} ({order[7]})", parse_mode="Markdown")
        bot.send_message(order[0], f"💚 *Payment Released!*\nRef: `{ref}`\nAmount: ₦{order[1]:,.0f}\n\nCheck your account 🎉", parse_mode="Markdown")
        bot.send_message(order[2], f"✅ Your order `{ref}` is complete. Enjoy! 🛍️")
    except Exception as e:
        bot.reply_to(message, f"Usage: /release [OT-XXXXXXXXX]\nError: {e}")

@bot.message_handler(commands=['freeze'])
def cmd_freeze(message):
    if message.chat.id != ADMIN_ID: return
    try:
        ref = message.text.split()[1].upper()
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE orders SET frozen = 1, status = 'FROZEN' WHERE reference = ?", (ref,))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"🔴 Order `{ref}` FROZEN.", parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"Usage: /freeze [OT-XXXXXXXXX]\nError: {e}")

@bot.message_handler(commands=['orders'])
def cmd_orders(message):
    if message.chat.id != ADMIN_ID: return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT reference, buyer_name, item_desc, gross_amount, status, frozen FROM orders ORDER BY created_at DESC LIMIT 20")
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.reply_to(message, "No orders yet.")
        return
    lines = ["📋 *Orders:*\n"]
    for r in rows:
        tag = " 🔴" if r[5] else ""
        lines.append(f"`{r[0]}`{tag}\n{r[1]} | {r[2]} | ₦{r[3]:,.0f} | {r[4]}\n")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['sellers'])
def cmd_sellers(message):
    if message.chat.id != ADMIN_ID: return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT seller_id, shop_name, is_approved FROM sellers ORDER BY joined_at DESC")
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.reply_to(message, "No sellers yet.")
        return
    lines = ["🏪 *Sellers:*\n"]
    for r in rows:
        lines.append(f"`{r[0]}` — *{r[1]}* | {'✅ Live' if r[2] else '⏳ Pending'}")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────
#  SELLER PRODUCT COMMANDS
# ─────────────────────────────────────────
@bot.message_handler(commands=['addproduct'])
def cmd_addproduct(message):
    if not is_seller(message.chat.id):
        bot.reply_to(message, "🚫 Approved sellers only.")
        return
    try:
        _, parts = message.text.split(maxsplit=1)
        cat, color, price, stock, gender = [p.strip() for p in parts.split(",")]
        conn = get_conn()
        c = conn.cursor()
        c.execute("INSERT INTO products (seller_id, category, color, price, stock, gender) VALUES (?, ?, ?, ?, ?, ?)",
                  (message.chat.id, cat.capitalize(), color.capitalize(), float(price), int(stock), gender.capitalize()))
        conn.commit()
        conn.close()
        bot.reply_to(message,
            f"✅ *{color.capitalize()} {cat.capitalize()}* added!\nPrice: ₦{float(price):,} | Stock: {stock} yds | {gender.capitalize()}",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message, f"⚠️ Format: /addproduct Category, Color, Price, Stock, Gender\nError: {e}")

@bot.message_handler(commands=['mystock'])
def cmd_mystock(message):
    if not is_seller(message.chat.id): return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, category, color, price, stock, gender FROM products WHERE seller_id = ?", (message.chat.id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.reply_to(message, "📭 No products yet. Use /addproduct")
        return
    lines = ["📦 *Your Catalog:*\n"]
    for r in rows:
        lines.append(f"[{r[0]}] *{r[2]} {r[1]}* — ₦{r[3]:,} | {r[4]} yds | {r[5]}")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['myorders'])
def cmd_myorders(message):
    if not is_seller(message.chat.id): return
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT reference, buyer_name, item_desc, quantity, gross_amount, seller_receives, status, frozen
                 FROM orders WHERE seller_id = ? ORDER BY created_at DESC LIMIT 15""", (message.chat.id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.reply_to(message, "No orders yet. Keep pushing! 💪")
        return
    lines = ["📋 *Your Orders:*\n"]
    for r in rows:
        tag = " 🔴" if r[7] else ""
        lines.append(f"`{r[0]}`{tag}\n{r[1]} | {r[2]} x{r[3]}\n₦{r[4]:,.0f} → You get ₦{r[5]:,.0f} | {r[6]}\n")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────
#  MAIN HANDLER
# ─────────────────────────────────────────
@bot.message_handler(content_types=['text', 'photo'])
def main_handler(message):
    user_id = message.chat.id
    text    = message.text.strip() if message.text else ""
    lower   = text.lower()

    # Seller registration trigger
    if lower in ["🏪 i want to sell", "i want to sell"]:
        start_seller_reg(message)
        return

    # Mid-registration seller
    if is_pending_seller(user_id):
        handle_seller_reg(message)
        return

    # Approved seller — send to dashboard unless they're buying
    if is_seller(user_id) and lower != "🛍️ i want to buy":
        seller_dashboard(message)
        return

    # Receipt photo
    if message.content_type == 'photo':
        handle_receipt(message)
        return

    # Buyer flow
    handle_buyer(message)

# ─────────────────────────────────────────
#  BUYER FLOW
# ─────────────────────────────────────────
def handle_buyer(message):
    user_id = message.chat.id
    text    = message.text.strip() if message.text else ""
    lower   = text.lower()

    session = get_session(user_id)
    # session: [0]state [1]category [2]gender [3]product_id [4]qty [5]seller_id

    # ── Buyer taps I want to buy — show shop list ──
    if lower == "🛍️ i want to buy":
        shops = get_shop_list()
        if not shops:
            bot.reply_to(message,
                "😔 No shops are open right now. Check back soon!",
                reply_markup=ReplyKeyboardRemove()
            )
            return

        lines = ["🏪 *OnTabs Marketplace*\n\nOpen shops right now:\n"]
        for sid, name, cats, cnt in shops:
            lines.append(f"🔹 *{name}*\n    {cats or 'Various'} — {cnt} item(s)\n")
        lines.append("Just type what you're looking for and I'll find it! 👇\n_(e.g. 'I need lace', 'senator for men')_")

        # Clear session
        conn = get_conn()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO buyer_sessions (user_id, state) VALUES (?, 'BROWSING')", (user_id,))
        conn.commit()
        conn.close()

        bot.reply_to(message, "\n".join(lines), parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())
        return

    # ── Gender keyboard response ──
    gender_map = {
        "👗 for a lady": "Female",
        "👔 for a man":  "Male",
        "🎁 it's a gift": "Unisex"
    }
    if lower in gender_map and session and session[0] == "WAITING_FOR_GENDER":
        gender = gender_map[lower]
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE buyer_sessions SET gender_pref = ?, state = 'WAITING_FOR_COLOR' WHERE user_id = ?",
                  (gender, user_id))
        conn.commit()
        conn.close()

        colors = get_colors(session[1], gender, session[5])
        color_list = format_colors(colors)
        if color_list:
            bot.send_message(user_id,
                f"✨ *{session[1]}* for {'Ladies 👗' if gender == 'Female' else 'Men 👔' if gender == 'Male' else 'anyone 🎁'}:\n\n"
                f"{color_list}\n\nWhich color? Just type it 👇",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            bot.send_message(user_id,
                f"😔 No *{session[1]}* available for {gender} right now. Try another category?",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            bot.send_message(ADMIN_ID, f"🚨 No {session[1]} for {gender}\nBuyer: `{user_id}`", parse_mode="Markdown")
        return

    # ── Category detection ──
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT DISTINCT category FROM products")
    all_cats = [row[0].lower() for row in c.fetchall()]
    conn.close()

    male_keys   = ["man", "male", "men", "groom", "atiku", "senator", "agbada"]
    female_keys = ["woman", "female", "lace", "chiffon", "silk", "bride", "asoebi"]
    detected_gender = (
        "Male"   if any(w in lower for w in male_keys) else
        "Female" if any(w in lower for w in female_keys) else
        None
    )

    matched_cat = next((cat for cat in all_cats if cat in lower), None)

    # ── Category found ──
    if matched_cat and (not session or session[0] in ("BROWSING", "START", None)):
        conn = get_conn()
        c = conn.cursor()
        c.execute("""SELECT DISTINCT p.seller_id FROM products p
                     JOIN sellers s ON p.seller_id = s.seller_id
                     WHERE p.category = ? AND s.is_approved = 1 LIMIT 1""", (matched_cat.capitalize(),))
        seller_row = c.fetchone()
        seller_id  = seller_row[0] if seller_row else None

        c.execute("""INSERT OR REPLACE INTO buyer_sessions
                     (user_id, state, current_category, gender_pref, current_seller_id)
                     VALUES (?, ?, ?, ?, ?)""",
                  (user_id, "WAITING_FOR_GENDER", matched_cat.capitalize(), detected_gender, seller_id))
        conn.commit()
        conn.close()

        if detected_gender:
            colors = get_colors(matched_cat.capitalize(), detected_gender, seller_id)
            color_list = format_colors(colors)
            conn2 = get_conn()
            c2 = conn2.cursor()
            c2.execute("UPDATE buyer_sessions SET state = 'WAITING_FOR_COLOR' WHERE user_id = ?", (user_id,))
            conn2.commit()
            conn2.close()
            if color_list:
                bot.reply_to(message,
                    f"{'Ehen!' if detected_gender == 'Male' else 'Yass!'} "
                    f"*{matched_cat.capitalize()}* for {'Men 👔' if detected_gender == 'Male' else 'Ladies 👗'} — we have:\n\n"
                    f"{color_list}\n\nWhich color? 👇",
                    parse_mode="Markdown"
                )
            else:
                bot.reply_to(message,
                    f"😔 Out of *{matched_cat.capitalize()}* for {detected_gender}s right now.\nBoss has been notified!",
                    parse_mode="Markdown"
                )
                bot.send_message(ADMIN_ID, f"🚨 No {matched_cat} for {detected_gender}\nBuyer: `{user_id}`", parse_mode="Markdown")
        else:
            bot.reply_to(message,
                f"*{matched_cat.capitalize()}!* Great taste 😍\n\nWho's it for?",
                reply_markup=gender_keyboard(),
                parse_mode="Markdown"
            )
        return

    # ── Color selection ──
    if session and session[0] == "WAITING_FOR_COLOR":
        category  = session[1]
        gender    = session[2] or "Unisex"
        seller_id = session[5]

        conn = get_conn()
        c = conn.cursor()
        c.execute("""SELECT id, color, price, stock FROM products
                     WHERE seller_id = ? AND category = ? AND color LIKE ?
                     AND (gender = ? OR gender = 'Unisex') COLLATE NOCASE""",
                  (seller_id, category, f"%{lower}%", gender))
        product = c.fetchone()

        if product:
            p_id, color, price, stock = product
            stock_label = f"{stock} yards available" if stock >= 0 else "In Stock ✅"
            c.execute("UPDATE buyer_sessions SET state = 'WAITING_FOR_QUANTITY', pending_product_id = ? WHERE user_id = ?",
                      (p_id, user_id))
            conn.commit()
            conn.close()
            bot.reply_to(message,
                f"Yes! *{color} {category}* 🎉\n\n💰 ₦{price:,}/yard\n📦 {stock_label}\n\nHow many yards? 👇",
                parse_mode="Markdown"
            )
        else:
            colors = get_colors(category, gender, seller_id)
            color_list = format_colors(colors)
            conn.close()
            if color_list:
                bot.reply_to(message,
                    f"🤔 No *{text}* in our {category} collection.\n\nWe have:\n\n{color_list}\n\nAny of these? 👀\n_(Flagged for Boss 📌)_",
                    parse_mode="Markdown"
                )
            else:
                bot.reply_to(message, f"😔 All out of *{category}* right now. Boss notified!", parse_mode="Markdown")
            bot.send_message(ADMIN_ID,
                f"🚨 *WAREHOUSE ALERT*\nBuyer wants *{text} {category}* ({gender})\nID: `{user_id}`",
                parse_mode="Markdown"
            )
        return

    # ── Quantity ──
    if session and session[0] == "WAITING_FOR_QUANTITY":
        if not lower.isdigit():
            bot.reply_to(message, "Please type a number — how many yards? 😊")
            return

        qty  = int(lower)
        p_id = session[3]
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT color, price, stock, category FROM products WHERE id = ?", (p_id,))
        product = c.fetchone()

        if not product:
            conn.close()
            bot.reply_to(message, "⚠️ Something went wrong. Type /start to begin again.")
            return

        color, price, stock, category = product

        if stock >= 0 and qty > stock:
            conn.close()
            bot.reply_to(message, f"😬 Only *{stock} yards* left! Enter a smaller amount.", parse_mode="Markdown")
            return

        gross = qty * price
        fee   = round(gross * ONTABS_FEE_PCT, 2)
        total = round(gross + fee, 2)

        c.execute("UPDATE buyer_sessions SET state = 'CONFIRMING', quantity = ? WHERE user_id = ?", (qty, user_id))
        conn.commit()
        conn.close()

        bot.reply_to(message,
            f"📊 *Order Summary*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Item: *{color} {category}*\n"
            f"For: {session[2] or 'Unisex'}\n"
            f"Qty: {qty} yards\n"
            f"Price: ₦{price:,}/yard\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Subtotal: ₦{gross:,.0f}\n"
            f"OnTabs Fee (0.5%): ₦{fee:,.0f}\n"
            f"*Total: ₦{total:,.0f}*\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
            f"Type *BUY* to proceed 🛒",
            parse_mode="Markdown"
        )
        return

    # ── BUY ──
    if "buy" in lower and session and session[0] == "CONFIRMING":
        p_id      = session[3]
        qty       = session[4]
        seller_id = session[5]

        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT color, price, category FROM products WHERE id = ?", (p_id,))
        product = c.fetchone()
        color, price, category = product

        gross       = qty * price
        fee         = round(gross * ONTABS_FEE_PCT, 2)
        total       = round(gross + fee, 2)
        seller_gets = gross - fee
        ref         = gen_reference()

        c.execute("""INSERT INTO orders
                     (reference, buyer_id, seller_id, product_id, buyer_name, item_desc,
                      quantity, unit_price, gross_amount, ontabs_fee, seller_receives,
                      status, frozen, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'AWAITING_PAYMENT', 1, ?)""",
                  (ref, user_id, seller_id, p_id,
                   message.from_user.first_name,
                   f"{color} {category}",
                   qty, price, gross, fee, seller_gets,
                   datetime.now().isoformat()))

        c.execute("UPDATE buyer_sessions SET state = 'AWAITING_RECEIPT' WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

        bot.reply_to(message,
            f"🛡️ *OnTabs Zero-Trust Escrow*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Pay into the OnTabs escrow account:\n\n"
            f"🏦 Bank: *{ESCROW_BANK}*\n"
            f"👤 Name: *{ESCROW_NAME}*\n"
            f"💳 Account: `{ESCROW_ACCOUNT}`\n\n"
            f"💰 *Amount: ₦{total:,.0f}*\n\n"
            f"🔑 *Reference:*\n`{ref}`\n\n"
            f"⚠️ _Use this reference when transferring._\n\n"
            f"📸 Send your receipt screenshot once done.",
            parse_mode="Markdown"
        )

        conn2 = get_conn()
        c2 = conn2.cursor()
        c2.execute("SELECT shop_name FROM sellers WHERE seller_id = ?", (seller_id,))
        shop = c2.fetchone()
        conn2.close()

        bot.send_message(seller_id,
            f"🔔 *New Order!*\nRef: `{ref}`\nItem: *{color} {category}* x{qty}\nValue: ₦{gross:,.0f}\nYou receive: ₦{seller_gets:,.0f}\n\n⏳ Awaiting buyer payment.",
            parse_mode="Markdown"
        )
        bot.send_message(ADMIN_ID,
            f"🛒 *NEW ORDER*\nRef: `{ref}`\nBuyer: {message.from_user.first_name} (`{user_id}`)\nItem: {color} {category} x{qty}\nTotal: ₦{total:,.0f}\nFee: ₦{fee:,.0f}\nSeller gets: ₦{seller_gets:,.0f}",
            parse_mode="Markdown"
        )
        return

# ─────────────────────────────────────────
#  RECEIPT HANDLER
# ─────────────────────────────────────────
def handle_receipt(message):
    user_id = message.chat.id
    session = get_session(user_id)

    if not session or session[0] != "AWAITING_RECEIPT":
        bot.reply_to(message, "Thanks! But I'm not expecting a receipt from you right now. Type /start for help 😊")
        return

    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT reference, seller_id, item_desc, quantity, gross_amount, seller_receives, product_id
                 FROM orders WHERE buyer_id = ? AND status = 'AWAITING_PAYMENT'
                 ORDER BY created_at DESC LIMIT 1""", (user_id,))
    order = c.fetchone()

    if not order:
        conn.close()
        bot.reply_to(message, "No pending order found. Type /start to begin again.")
        return

    ref, seller_id, item_desc, qty, gross, seller_gets, p_id = order
    c.execute("SELECT delivery_hrs, shop_name FROM sellers WHERE seller_id = ?", (seller_id,))
    seller_info = c.fetchone()
    delivery_hrs = seller_info[0] if seller_info else 24
    shop_name    = seller_info[1] if seller_info else "the seller"
    release_at   = datetime.now() + timedelta(hours=delivery_hrs)

    c.execute("UPDATE orders SET status = 'PAID', paid_at = ?, release_at = ? WHERE reference = ?",
              (datetime.now().isoformat(), release_at.isoformat(), ref))
    c.execute("UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= 0", (qty, p_id))
    c.execute("UPDATE buyer_sessions SET state = 'BROWSING' WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    bot.reply_to(message,
        f"✅ *Receipt received!*\n\nRef: `{ref}`\n🔒 Funds held in escrow.\n⏰ Auto-releases to {shop_name} in *{delivery_hrs} hours*.\n\nYour item is on its way! 🎉",
        parse_mode="Markdown"
    )
    bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
    bot.send_message(ADMIN_ID,
        f"📸 *Receipt*\nRef: `{ref}`\nBuyer: {message.from_user.first_name} (`{user_id}`)\nItem: {item_desc} x{qty}\nAmount: ₦{gross:,.0f}\nAuto-release: {release_at.strftime('%d %b, %I:%M %p')}\n\n/release {ref} — Release\n/freeze {ref} — Freeze",
        parse_mode="Markdown"
    )
    bot.send_message(seller_id,
        f"💛 *Payment Confirmed!*\nRef: `{ref}`\nItem: {item_desc} x{qty}\nYou earn: ₦{seller_gets:,.0f} (in escrow)\n\nDispatch now! 🚚",
        parse_mode="Markdown"
    )

# ─────────────────────────────────────────
#  AUTO RELEASE + REPOST
# ─────────────────────────────────────────
def auto_release_check():
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("""SELECT o.reference, o.buyer_id, o.seller_id, o.seller_receives, s.bank_name, s.account_no
                 FROM orders o JOIN sellers s ON o.seller_id = s.seller_id
                 WHERE o.status = 'PAID' AND o.frozen = 1 AND o.release_at <= ?""", (now,))
    for order in c.fetchall():
        ref, buyer_id, seller_id, seller_gets, bank, acc = order
        c.execute("UPDATE orders SET frozen = 0, status = 'RELEASED', released_at = ? WHERE reference = ?",
                  (datetime.now().isoformat(), ref))
        conn.commit()
        bot.send_message(ADMIN_ID, f"⏰ Auto-Released `{ref}` — ₦{seller_gets:,.0f}", parse_mode="Markdown")
        bot.send_message(seller_id, f"💚 Funds released!\nRef: `{ref}`\nAmount: ₦{seller_gets:,.0f}\nCheck {bank} — {acc} 🎉", parse_mode="Markdown")
        bot.send_message(buyer_id, f"✅ Order `{ref}` complete. Thanks for shopping on OnTabs! 🛍️")
    conn.close()

def auto_repost():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT seller_id, shop_name, group_id FROM sellers WHERE group_id IS NOT NULL AND is_approved = 1")
    for seller_id, shop_name, group_id in c.fetchall():
        c.execute("SELECT category, color, price, stock FROM products WHERE seller_id = ?", (seller_id,))
        items = c.fetchall()
        if not items:
            continue
        p_list = "\n".join([f"🔹 {r[1]} {r[0]}: ₦{r[2]:,} ({r[3]} yds)" if r[3] >= 0 else f"🔹 {r[1]} {r[0]}: ₦{r[2]:,}" for r in items])
        try:
            bot.send_message(group_id, f"🌅 *{shop_name} — Today's Collection*\n\n{p_list}\n\nDM to order 👆", parse_mode="Markdown")
        except Exception as e:
            print(f"Repost failed: {e}")
    conn.close()

# ─────────────────────────────────────────
#  LAUNCH
# ─────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(auto_repost,        'cron',    hour=8, minute=0)
    scheduler.add_job(auto_release_check, 'interval', minutes=30)
    scheduler.start()
    print("✅ OnTabs v4 is LIVE.")
    bot.infinity_polling()
