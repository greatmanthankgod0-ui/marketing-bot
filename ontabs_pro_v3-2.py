import os
import random
import sqlite3
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────
TOKEN    = os.environ.get("BOT_TOKEN", "YOUR_TOKEN_HERE")
ADMIN_ID = int(os.environ.get("ADMIN_ID", "123456789"))

# OnTabs Escrow Account — set these to your real details
ESCROW_BANK    = os.environ.get("ESCROW_BANK", "GTBank")
ESCROW_NAME    = os.environ.get("ESCROW_NAME", "OnTabs Business Inc")
ESCROW_ACCOUNT = os.environ.get("ESCROW_ACCOUNT", "0123456789")
ONTABS_FEE_PCT = 0.005  # 0.5%

bot = telebot.TeleBot(TOKEN)
DB  = "ontabs_pro.db"

# ─────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    # Sellers table
    c.execute('''CREATE TABLE IF NOT EXISTS sellers (
        seller_id   INTEGER PRIMARY KEY,
        shop_name   TEXT,
        bank_name   TEXT,
        account_no  TEXT,
        account_name TEXT,
        delivery_hrs INTEGER DEFAULT 24,
        is_approved INTEGER DEFAULT 0,
        joined_at   TEXT
    )''')

    # Products — tied to seller
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id   INTEGER,
        category    TEXT,
        color       TEXT,
        price       REAL,
        stock       INTEGER DEFAULT -1,
        gender      TEXT DEFAULT 'Unisex'
    )''')

    # Buyer sessions
    c.execute('''CREATE TABLE IF NOT EXISTS buyer_sessions (
        user_id         INTEGER PRIMARY KEY,
        role            TEXT DEFAULT 'buyer',
        current_category TEXT,
        current_seller_id INTEGER,
        state           TEXT,
        gender_pref     TEXT,
        pending_product_id INTEGER,
        quantity        INTEGER DEFAULT 0
    )''')

    # Seller registration sessions
    c.execute('''CREATE TABLE IF NOT EXISTS seller_sessions (
        seller_id   INTEGER PRIMARY KEY,
        state       TEXT,
        shop_name   TEXT,
        bank_name   TEXT,
        account_no  TEXT,
        account_name TEXT,
        delivery_hrs INTEGER
    )''')

    # Orders / Escrow ledger
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
        receipt_url     TEXT,
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
    """Generate a unique 9-digit OT reference number."""
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

def get_buyer_session(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT current_category, state, gender_pref, pending_product_id, 
                 quantity, current_seller_id FROM buyer_sessions WHERE user_id = ?""", (user_id,))
    result = c.fetchone()
    conn.close()
    return result
    # [0]category [1]state [2]gender [3]product_id [4]qty [5]seller_id

def available_colors(category, gender, seller_id=None):
    """Return all available colors for a category filtered by gender."""
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

def format_color_list(rows):
    if not rows:
        return None
    lines = []
    for color, price, stock in rows:
        stock_label = f"{stock} yds" if stock >= 0 else "In Stock"
        lines.append(f"🔹 {color} — ₦{price:,} ({stock_label})")
    return "\n".join(lines)

# ─────────────────────────────────────────
#  /start — Smart Router
# ─────────────────────────────────────────
@bot.message_handler(commands=['start'])
def handle_start(message):
    user_id = message.chat.id
    name    = message.from_user.first_name

    # Already approved seller
    if is_seller(user_id):
        seller_dashboard(message)
        return

    # Mid-registration seller
    if is_pending_seller(user_id):
        bot.reply_to(message, "👋 You're still setting up your shop! Let's continue from where we stopped 😊")
        handle_seller_registration(message)
        return

    # Admin
    if user_id == ADMIN_ID:
        bot.reply_to(message,
            f"👑 *Welcome back, Boss!*\n\n"
            f"*OnTabs Admin Commands:*\n"
            f"/approve [seller\\_id] — Approve a seller\n"
            f"/freeze [order\\_ref] — Freeze an order\n"
            f"/release [order\\_ref] — Release funds to seller\n"
            f"/orders — View all pending orders\n"
            f"/sellers — View all registered sellers",
            parse_mode="Markdown"
        )
        return

    # New user — ask buyer or seller
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
#  SELLER REGISTRATION FLOW
# ─────────────────────────────────────────
def start_seller_registration(message):
    user_id = message.chat.id
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO seller_sessions (seller_id, state) VALUES (?, ?)",
              (user_id, "ASK_SHOP_NAME"))
    conn.commit()
    conn.close()
    bot.send_message(user_id,
        "🏪 *Let's set up your OnTabs Shop!*\n\n"
        "This takes less than 2 minutes. Your shop will be reviewed and approved before going live.\n\n"
        "First things first — *what's the name of your shop?* 👇",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

def seller_dashboard(message):
    user_id = message.chat.id
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT shop_name, delivery_hrs FROM sellers WHERE seller_id = ?", (user_id,))
    seller = c.fetchone()
    c.execute("SELECT COUNT(*) FROM orders WHERE seller_id = ? AND status = 'AWAITING_PAYMENT'", (user_id,))
    pending = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM orders WHERE seller_id = ? AND status = 'PAID' AND frozen = 1", (user_id,))
    frozen  = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(seller_receives),0) FROM orders WHERE seller_id = ? AND status = 'RELEASED'", (user_id,))
    earned  = c.fetchone()[0]
    conn.close()

    bot.send_message(user_id,
        f"👋 Welcome back, *{seller[0]}!*\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔴 Awaiting Payment: *{pending}*\n"
        f"🟡 Funds in Escrow: *{frozen}*\n"
        f"✅ Total Released: *₦{earned:,.0f}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"*Seller Commands:*\n"
        f"/addproduct — Add a new fabric\n"
        f"/mystock — View your catalog\n"
        f"/myorders — View your orders\n"
        f"/settings — Update shop details",
        parse_mode="Markdown"
    )

def handle_seller_registration(message):
    user_id = message.chat.id
    text    = message.text.strip()
    sess    = get_seller_session(user_id)
    if not sess:
        return
    state = sess[0]

    conn = get_conn()
    c = conn.cursor()

    if state == "ASK_SHOP_NAME":
        c.execute("UPDATE seller_sessions SET shop_name = ?, state = ? WHERE seller_id = ?",
                  (text, "ASK_BANK_NAME", user_id))
        conn.commit()
        conn.close()
        bot.send_message(user_id,
            f"Love it! *{text}* 🔥\n\n"
            f"Now, which bank will you be receiving payments to?\n"
            f"_(e.g. GTBank, Access Bank, Opay, Palmpay)_",
            parse_mode="Markdown"
        )

    elif state == "ASK_BANK_NAME":
        c.execute("UPDATE seller_sessions SET bank_name = ?, state = ? WHERE seller_id = ?",
                  (text, "ASK_ACCOUNT_NO", user_id))
        conn.commit()
        conn.close()
        bot.send_message(user_id,
            f"Got it — *{text}* ✅\n\n"
            f"What's your *account number?* 👇",
            parse_mode="Markdown"
        )

    elif state == "ASK_ACCOUNT_NO":
        if not text.isdigit() or len(text) < 10:
            conn.close()
            bot.send_message(user_id, "⚠️ That doesn't look right. Please enter a valid 10-digit account number.")
            return
        c.execute("UPDATE seller_sessions SET account_no = ?, state = ? WHERE seller_id = ?",
                  (text, "ASK_ACCOUNT_NAME", user_id))
        conn.commit()
        conn.close()
        bot.send_message(user_id, "Perfect! 👌\n\nWhat's the *account name* on that account?",
                         parse_mode="Markdown")

    elif state == "ASK_ACCOUNT_NAME":
        c.execute("UPDATE seller_sessions SET account_name = ?, state = ? WHERE seller_id = ?",
                  (text, "ASK_DELIVERY_HRS", user_id))
        conn.commit()
        conn.close()
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.row(KeyboardButton("6 hours"), KeyboardButton("12 hours"))
        kb.row(KeyboardButton("24 hours"), KeyboardButton("48 hours"))
        bot.send_message(user_id,
            f"Almost done! 🎉\n\n"
            f"How long does it typically take for your orders to reach the buyer?\n"
            f"_(This sets the escrow release timer — funds are held until this time passes)_",
            reply_markup=kb,
            parse_mode="Markdown"
        )

    elif state == "ASK_DELIVERY_HRS":
        hrs_map = {"6 hours": 6, "12 hours": 12, "24 hours": 24, "48 hours": 48}
        hrs = hrs_map.get(text)
        if not hrs:
            conn.close()
            bot.send_message(user_id, "Please pick one of the options above 👆")
            return

        # Pull all session data and save to sellers table
        c.execute("SELECT shop_name, bank_name, account_no, account_name FROM seller_sessions WHERE seller_id = ?",
                  (user_id,))
        s = c.fetchone()
        c.execute("""INSERT OR REPLACE INTO sellers 
                     (seller_id, shop_name, bank_name, account_no, account_name, delivery_hrs, is_approved, joined_at)
                     VALUES (?, ?, ?, ?, ?, ?, 0, ?)""",
                  (user_id, s[0], s[1], s[2], s[3], hrs, datetime.now().isoformat()))
        c.execute("DELETE FROM seller_sessions WHERE seller_id = ?", (user_id,))
        conn.commit()
        conn.close()

        bot.send_message(user_id,
            f"🎊 *Application Submitted!*\n\n"
            f"Shop: *{s[0]}*\n"
            f"Bank: {s[1]} — {s[2]} ({s[3]})\n"
            f"Delivery Window: {hrs} hours\n\n"
            f"Your shop is being reviewed by OnTabs. You'll get notified once you're approved! 🚀",
            parse_mode="Markdown",
            reply_markup=ReplyKeyboardRemove()
        )

        # Notify admin
        bot.send_message(ADMIN_ID,
            f"🏪 *NEW SELLER APPLICATION*\n\n"
            f"Name: {message.from_user.first_name}\n"
            f"ID: `{user_id}`\n"
            f"Shop: *{s[0]}*\n"
            f"Bank: {s[1]} — {s[2]}\n"
            f"Account Name: {s[3]}\n"
            f"Delivery: {hrs}hrs\n\n"
            f"Reply /approve {user_id} to activate their shop.",
            parse_mode="Markdown"
        )

# ─────────────────────────────────────────
#  ADMIN COMMANDS
# ─────────────────────────────────────────
@bot.message_handler(commands=['approve'])
def approve_seller(message):
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
        bot.reply_to(message, f"✅ *{shop[0]}* is now live on OnTabs!", parse_mode="Markdown")
        bot.send_message(seller_id,
            f"🎉 *Congratulations! Your shop is LIVE!*\n\n"
            f"Welcome to OnTabs! Start adding your products with /addproduct\n\n"
            f"Type /start to see your dashboard 🚀",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message, f"Usage: /approve [seller_id]\nError: {e}")

@bot.message_handler(commands=['release'])
def admin_release(message):
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

        bot.reply_to(message,
            f"✅ *Funds Released!*\n\n"
            f"Ref: `{ref}`\n"
            f"Shop: {order[4]}\n"
            f"Amount: ₦{order[1]:,.0f}\n"
            f"To: {order[5]} — {order[6]} ({order[7]})",
            parse_mode="Markdown"
        )
        # Notify seller
        bot.send_message(order[0],
            f"💚 *Payment Released!*\n\n"
            f"Order: `{ref}`\n"
            f"Item: {order[3]}\n"
            f"Amount: *₦{order[1]:,.0f}*\n\n"
            f"Check your account — OnTabs has released your funds! 🎉",
            parse_mode="Markdown"
        )
        # Notify buyer
        bot.send_message(order[2],
            f"✅ Your order is confirmed and funds have been released to the seller.\n"
            f"Enjoy your fabric! 🛍️",
        )
    except Exception as e:
        bot.reply_to(message, f"Usage: /release [OT-XXXXXXXXX]\nError: {e}")

@bot.message_handler(commands=['freeze'])
def admin_freeze(message):
    if message.chat.id != ADMIN_ID: return
    try:
        ref = message.text.split()[1].upper()
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE orders SET frozen = 1, status = 'FROZEN' WHERE reference = ?", (ref,))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"🔴 Order `{ref}` has been *FROZEN*. No funds will move until you release it.",
                     parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"Usage: /freeze [OT-XXXXXXXXX]\nError: {e}")

@bot.message_handler(commands=['orders'])
def admin_orders(message):
    if message.chat.id != ADMIN_ID: return
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT reference, buyer_name, item_desc, gross_amount, status, frozen
                 FROM orders ORDER BY created_at DESC LIMIT 20""")
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.reply_to(message, "No orders yet.")
        return
    lines = ["📋 *Recent Orders:*\n"]
    for r in rows:
        frozen_tag = "🔴 FROZEN" if r[5] else ""
        lines.append(f"`{r[0]}` — {r[1]}\n{r[2]} | ₦{r[3]:,.0f} | {r[4]} {frozen_tag}\n")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['sellers'])
def admin_sellers(message):
    if message.chat.id != ADMIN_ID: return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT seller_id, shop_name, is_approved, joined_at FROM sellers ORDER BY joined_at DESC")
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.reply_to(message, "No sellers yet.")
        return
    lines = ["🏪 *Registered Sellers:*\n"]
    for r in rows:
        status = "✅ Live" if r[2] else "⏳ Pending"
        lines.append(f"`{r[0]}` — *{r[1]}* | {status}")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────
#  SELLER COMMANDS (Post-Approval)
# ─────────────────────────────────────────
@bot.message_handler(commands=['addproduct'])
def add_product(message):
    if not is_seller(message.chat.id):
        bot.reply_to(message, "🚫 This command is for approved sellers only.")
        return
    try:
        _, parts = message.text.split(maxsplit=1)
        cat, color, price, stock, gender = [p.strip() for p in parts.split(",")]
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO products (seller_id, category, color, price, stock, gender) VALUES (?, ?, ?, ?, ?, ?)",
            (message.chat.id, cat.capitalize(), color.capitalize(), float(price), int(stock), gender.capitalize())
        )
        conn.commit()
        conn.close()
        stock_label = f"{stock} yards" if int(stock) >= 0 else "Unlimited"
        bot.reply_to(message,
            f"✅ Added to your catalog!\n\n"
            f"*{color.capitalize()} {cat.capitalize()}*\n"
            f"Price: ₦{float(price):,}/yard | Stock: {stock_label} | {gender.capitalize()}",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message,
            "⚠️ Format: `/addproduct Category, Color, Price, Stock, Gender`\n"
            "Example: `/addproduct Lace, Royal Blue, 5000, 20, Female`\n\n"
            f"Error: {e}", parse_mode="Markdown"
        )

@bot.message_handler(commands=['mystock'])
def my_stock(message):
    if not is_seller(message.chat.id): return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, category, color, price, stock, gender FROM products WHERE seller_id = ?",
              (message.chat.id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.reply_to(message, "📭 Your catalog is empty. Use /addproduct to add items.")
        return
    lines = ["📦 *Your Catalog:*\n"]
    for r in rows:
        stock_label = f"{r[4]} yds" if r[4] >= 0 else "Unlimited"
        lines.append(f"[{r[0]}] *{r[2]} {r[1]}* — ₦{r[3]:,} | {stock_label} | {r[5]}")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['myorders'])
def my_orders(message):
    if not is_seller(message.chat.id): return
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT reference, buyer_name, item_desc, quantity, gross_amount, 
                        seller_receives, status, frozen, created_at
                 FROM orders WHERE seller_id = ? ORDER BY created_at DESC LIMIT 15""",
              (message.chat.id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.reply_to(message, "No orders yet. Keep pushing! 💪")
        return
    lines = ["📋 *Your Orders:*\n"]
    for r in rows:
        frozen_tag = " 🔴" if r[7] else ""
        lines.append(
            f"`{r[0]}`{frozen_tag}\n"
            f"Buyer: {r[1]} | {r[2]} x{r[3]}\n"
            f"Total: ₦{r[4]:,.0f} → You get: ₦{r[5]:,.0f}\n"
            f"Status: {r[6]}\n"
        )
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────
#  MAIN MESSAGE HANDLER — Buyer + Seller Router
# ─────────────────────────────────────────
@bot.message_handler(content_types=['text', 'photo'])
def main_handler(message):
    user_id = message.chat.id
    text    = message.text.strip() if message.text else ""
    lower   = text.lower()

    # ── Route: New seller wanting to register ──
    if lower in ["🏪 i want to sell", "sell", "i want to sell"]:
        start_seller_registration(message)
        return

    # ── Route: Seller mid-registration ──
    if is_pending_seller(user_id):
        handle_seller_registration(message)
        return

    # ── Route: Approved seller dashboard ──
    if is_seller(user_id) and lower not in ["🛍️ i want to buy"]:
        seller_dashboard(message)
        return

    # ── Route: Buyer taps I want to buy ──
    if lower == "🛍️ i want to buy":
        show_shop_list(message)
        return

    # ── Route: Buyer picking a shop by number ──
    session = get_buyer_session(user_id)
    if session and session[1] == "PICKING_SHOP" and text.isdigit():
        handle_shop_pick(message)
        return

    # ── Route: Receipt photo from buyer ──
    if message.content_type == 'photo':
        handle_receipt(message)
        return

    # ── Route: Buyer browsing flow ──
    handle_buyer(message)


# ─────────────────────────────────────────
#  SHOP BROWSER
# ─────────────────────────────────────────
def show_shop_list(message):
    user_id = message.chat.id
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT s.seller_id, s.shop_name,
                        GROUP_CONCAT(DISTINCT p.category) as cats,
                        COUNT(p.id) as product_count
                 FROM sellers s
                 LEFT JOIN products p ON s.seller_id = p.seller_id
                 WHERE s.is_approved = 1
                 GROUP BY s.seller_id ORDER BY s.shop_name""")
    shops = c.fetchall()
    conn.close()

    valid_shops = [(s[0], s[1], s[2], s[3]) for s in shops if s[3] and s[3] > 0]

    if not valid_shops:
        bot.send_message(user_id,
            "No shops are open right now. Check back soon!",
            reply_markup=ReplyKeyboardRemove())
        return

    lines = ["*OnTabs Marketplace*\n\nHere are our open shops:\n"]
    for i, (sid, name, cats, count) in enumerate(valid_shops, 1):
        cat_label = cats if cats else "Various"
        lines.append(f"*{i}.* {name}\n    {cat_label} - {count} item(s)\n")
    lines.append("Type the *number* of the shop you want to browse or just type what you need")

    import json
    conn2 = get_conn()
    c2 = conn2.cursor()
    c2.execute("""INSERT OR REPLACE INTO buyer_sessions
                 (user_id, state, current_category, gender_pref, pending_product_id, quantity, current_seller_id)
                 VALUES (?, ?, ?, NULL, NULL, 0, NULL)""",
              (user_id, "PICKING_SHOP", json.dumps([s[0] for s in valid_shops])))
    conn2.commit()
    conn2.close()

    bot.send_message(user_id, "\n".join(lines), parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())


def handle_shop_pick(message):
    user_id = message.chat.id
    text    = message.text.strip()
    import json

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT current_category FROM buyer_sessions WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()

    try:
        valid_shops = json.loads(row[0]) if row else []
    except:
        valid_shops = []

    idx = int(text) - 1
    if idx < 0 or idx >= len(valid_shops):
        bot.reply_to(message, f"Please pick a number between 1 and {len(valid_shops)}")
        return

    seller_id = valid_shops[idx]
    conn2 = get_conn()
    c2 = conn2.cursor()
    c2.execute("SELECT shop_name FROM sellers WHERE seller_id = ?", (seller_id,))
    shop = c2.fetchone()
    c2.execute("SELECT DISTINCT category FROM products WHERE seller_id = ?", (seller_id,))
    cats = [r[0] for r in c2.fetchall()]
    conn2.close()

    if not cats:
        bot.reply_to(message, f"This shop has no products yet.")
        return

    conn3 = get_conn()
    c3 = conn3.cursor()
    c3.execute("""INSERT OR REPLACE INTO buyer_sessions
                 (user_id, state, current_seller_id, current_category, gender_pref, pending_product_id, quantity)
                 VALUES (?, ?, ?, NULL, NULL, NULL, 0)""",
              (user_id, "WAITING_FOR_CATEGORY", seller_id))
    conn3.commit()
    conn3.close()

    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    for cat in cats:
        kb.add(KeyboardButton(cat))

    bot.send_message(user_id,
        f"You are browsing *{shop[0]}*!\n\nWhat are you looking for? Pick a category or just type",
        reply_markup=kb, parse_mode="Markdown")

# ─────────────────────────────────────────
#  BUYER FLOW
# ─────────────────────────────────────────
def handle_buyer(message):
    user_id = message.chat.id
    text    = message.text.strip() if message.text else ""
    lower   = text.lower()

    conn = get_conn()
    c = conn.cursor()
    session = get_buyer_session(user_id)
    # session: [0]category [1]state [2]gender [3]product_id [4]qty [5]seller_id

    # ── GENDER SELECTION (from keyboard) ──
    gender_map = {
        "👗 for a lady": "Female",
        "👔 for a man":  "Male",
        "🎁 it's a gift": "Unisex"
    }
    if lower in gender_map and session and session[1] == "WAITING_FOR_GENDER":
        gender = gender_map[lower]
        c.execute("UPDATE buyer_sessions SET gender_pref = ?, state = 'WAITING_FOR_COLOR' WHERE user_id = ?",
                  (gender, user_id))
        conn.commit()

        # Show available colors for this category + gender
        colors = available_colors(session[0], gender, session[5])
        color_list = format_color_list(colors)

        if color_list:
            bot.send_message(user_id,
                f"✨ Here's what we have in *{session[0]}* for {'Ladies 👗' if gender == 'Female' else 'Men 👔' if gender == 'Male' else 'anyone 🎁'}:\n\n"
                f"{color_list}\n\n"
                f"Which color catches your eye? Just type it! 👇",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            bot.send_message(user_id,
                f"Hmm 😔 We don't have any *{session[0]}* for that gender right now.\n"
                f"I've flagged it for the Boss! Try another category?",
                parse_mode="Markdown",
                reply_markup=ReplyKeyboardRemove()
            )
            bot.send_message(ADMIN_ID,
                f"🚨 *STOCK ALERT*\nNo {session[0]} available for {gender}\nBuyer ID: `{user_id}`",
                parse_mode="Markdown"
            )
            c.execute("UPDATE buyer_sessions SET state = 'START' WHERE user_id = ?", (user_id,))
            conn.commit()
        conn.close()
        return

    # ── SHOP CATEGORY PICK (buyer picked a shop and now picks category) ──
    if session and session[1] == "WAITING_FOR_CATEGORY":
        seller_id = session[5]
        conn.close()
        # Treat their text as a category selection and jump into buyer flow
        c2 = get_conn().cursor()
        conn2 = get_conn()
        c2 = conn2.cursor()
        c2.execute("UPDATE buyer_sessions SET state = ?, current_category = ? WHERE user_id = ?",
                  ("WAITING_FOR_GENDER", text.capitalize(), user_id))
        conn2.commit()
        conn2.close()
        bot.send_message(user_id,
            f"Got it! Who is the *{text.capitalize()}* for?",
            reply_markup=gender_keyboard(),
            parse_mode="Markdown"
        )
        return

    # ── CATEGORY DETECTION ──
    # Pull all categories from DB
    c.execute("SELECT DISTINCT category FROM products")
    all_cats = [row[0].lower() for row in c.fetchall()]

    # Gender keywords
    male_keys   = ["man", "male", "men", "groom", "atiku", "senator", "agbada"]
    female_keys = ["woman", "female", "lace", "chiffon", "silk", "bride", "aso-ebi", "asoebi"]
    detected_gender = (
        "Male"   if any(w in lower for w in male_keys) else
        "Female" if any(w in lower for w in female_keys) else
        None  # None = we need to ask
    )

    matched_cat = next((cat for cat in all_cats if cat in lower), None)

    # ── LEVEL 1: Category found ──
    if matched_cat and (not session or session[1] in ("START", None)):
        # Find which seller has this (for now, pick first approved seller with this product)
        c.execute("""SELECT DISTINCT p.seller_id FROM products p
                     JOIN sellers s ON p.seller_id = s.seller_id
                     WHERE p.category = ? AND s.is_approved = 1 LIMIT 1""", (matched_cat.capitalize(),))
        seller_row = c.fetchone()
        seller_id  = seller_row[0] if seller_row else None

        c.execute("""INSERT OR REPLACE INTO buyer_sessions 
                     (user_id, current_category, state, gender_pref, current_seller_id)
                     VALUES (?, ?, ?, ?, ?)""",
                  (user_id, matched_cat.capitalize(), "WAITING_FOR_GENDER", detected_gender, seller_id))
        conn.commit()

        if detected_gender:
            # Gender already detected — skip asking, show colors directly
            colors = available_colors(matched_cat.capitalize(), detected_gender, seller_id)
            color_list = format_color_list(colors)
            c.execute("UPDATE buyer_sessions SET state = 'WAITING_FOR_COLOR' WHERE user_id = ?", (user_id,))
            conn.commit()
            if color_list:
                bot.reply_to(message,
                    f"{'Ehen!' if detected_gender == 'Male' else 'Yass!'} {'👔' if detected_gender == 'Male' else '👗'} "
                    f"*{matched_cat.capitalize()}* for {'Men' if detected_gender == 'Male' else 'Ladies'} — we've got you covered!\n\n"
                    f"Here's what's available:\n\n{color_list}\n\n"
                    f"Which color do you want? 👇",
                    parse_mode="Markdown"
                )
            else:
                bot.reply_to(message,
                    f"Aww 😔 We're out of *{matched_cat.capitalize()}* for {detected_gender}s right now.\n"
                    f"The Boss has been notified! Want to try another category?",
                    parse_mode="Markdown"
                )
                bot.send_message(ADMIN_ID,
                    f"🚨 *STOCK ALERT*\nNo {matched_cat} for {detected_gender}\nBuyer: `{user_id}`",
                    parse_mode="Markdown"
                )
        else:
            # Need to ask gender
            bot.reply_to(message,
                f"Ooh, *{matched_cat.capitalize()}!* Great taste 😍\n\nQuick one — who's it for?",
                reply_markup=gender_keyboard(),
                parse_mode="Markdown"
            )
        conn.close()
        return

    # ── LEVEL 2: Color selection ──
    if session and session[1] == "WAITING_FOR_COLOR":
        category  = session[0]
        gender    = session[2] or "Unisex"
        seller_id = session[5]

        c.execute("""SELECT id, color, price, stock FROM products
                     WHERE seller_id = ? AND category = ? AND color LIKE ?
                     AND (gender = ? OR gender = 'Unisex') COLLATE NOCASE""",
                  (seller_id, category, f"%{lower}%", gender))
        product = c.fetchone()

        if product:
            p_id, color, price, stock = product
            stock_label = f"{stock} yards available" if stock >= 0 else "In Stock ✅"
            c.execute("""UPDATE buyer_sessions SET state = 'WAITING_FOR_QUANTITY', 
                         pending_product_id = ? WHERE user_id = ?""", (p_id, user_id))
            conn.commit()
            conn.close()
            bot.reply_to(message,
                f"Yes! We have *{color} {category}* 🎉\n\n"
                f"💰 Price: ₦{price:,} per yard\n"
                f"📦 {stock_label}\n\n"
                f"How many yards do you need? 👇",
                parse_mode="Markdown"
            )
        else:
            # Color not found — show full available list
            colors = available_colors(category, gender, seller_id)
            color_list = format_color_list(colors)
            conn.close()

            if color_list:
                bot.reply_to(message,
                    f"Hmm 🤔 I don't see *{text}* in our {category} collection right now.\n\n"
                    f"But here's what we DO have:\n\n{color_list}\n\n"
                    f"Any of these work for you? 👀\n"
                    f"_(Your request has been flagged for the Boss 📌)_",
                    parse_mode="Markdown"
                )
            else:
                bot.reply_to(message,
                    f"We're all out of *{category}* right now 😔\n"
                    f"The Boss has been notified. Check back soon!",
                    parse_mode="Markdown"
                )

            bot.send_message(ADMIN_ID,
                f"🚨 *WAREHOUSE ALERT*\n"
                f"Buyer `{user_id}` wants *{text} {category}* ({gender})\n"
                f"Not in stock — worth restocking? 👀",
                parse_mode="Markdown"
            )
        return

    # ── LEVEL 3: Quantity ──
    if session and session[1] == "WAITING_FOR_QUANTITY":
        if not lower.isdigit():
            conn.close()
            bot.reply_to(message, "Please type a number — how many yards do you need? 😊")
            return

        qty  = int(lower)
        p_id = session[3]

        c.execute("SELECT color, price, stock, category FROM products WHERE id = ?", (p_id,))
        product = c.fetchone()

        if not product:
            conn.close()
            bot.reply_to(message, "⚠️ Something went wrong. Please type /start to begin again.")
            return

        color, price, stock, category = product

        if stock >= 0 and qty > stock:
            conn.close()
            bot.reply_to(message,
                f"😬 We only have *{stock} yards* left! Please enter a smaller amount.",
                parse_mode="Markdown"
            )
            return

        gross   = qty * price
        fee     = round(gross * ONTABS_FEE_PCT, 2)
        total   = round(gross + fee, 2)

        c.execute("UPDATE buyer_sessions SET state = 'CONFIRMING', quantity = ? WHERE user_id = ?",
                  (qty, user_id))
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
            f"Type *BUY* to get payment details 🛒",
            parse_mode="Markdown"
        )
        return

    # ── LEVEL 4: BUY confirmation ──
    if "buy" in lower and session and session[1] == "CONFIRMING":
        p_id      = session[3]
        qty       = session[4]
        seller_id = session[5]

        c.execute("SELECT color, price, category FROM products WHERE id = ?", (p_id,))
        product = c.fetchone()
        color, price, category = product

        gross   = qty * price
        fee     = round(gross * ONTABS_FEE_PCT, 2)
        total   = round(gross + fee, 2)
        seller_gets = gross - fee

        ref = gen_reference()

        # Save order
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
        conn.commit()

        c.execute("UPDATE buyer_sessions SET state = 'AWAITING_RECEIPT' WHERE user_id = ?", (user_id,))
        conn.commit()
        conn.close()

        # Send payment details to buyer
        bot.reply_to(message,
            f"🛡️ *OnTabs Zero-Trust Escrow*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Your order is secured! Pay into the OnTabs escrow account below.\n"
            f"Your funds are protected until your item is delivered ✅\n\n"
            f"🏦 *Payment Details:*\n"
            f"Bank: *{ESCROW_BANK}*\n"
            f"Account Name: *{ESCROW_NAME}*\n"
            f"Account Number: `{ESCROW_ACCOUNT}`\n\n"
            f"💰 *Amount to Pay: ₦{total:,.0f}*\n\n"
            f"🔑 *Your Reference Number:*\n"
            f"`{ref}`\n\n"
            f"⚠️ _Use this reference when making the transfer so we can identify your payment._\n\n"
            f"📸 Once you've paid, send your receipt screenshot here.",
            parse_mode="Markdown"
        )

        # Notify seller (they see the order but NOT the money yet)
        c2 = get_conn().cursor()
        conn2 = get_conn()
        c2 = conn2.cursor()
        c2.execute("SELECT shop_name FROM sellers WHERE seller_id = ?", (seller_id,))
        shop = c2.fetchone()
        conn2.close()

        bot.send_message(seller_id,
            f"🔔 *New Order Alert!*\n\n"
            f"Ref: `{ref}`\n"
            f"Item: *{color} {category}*\n"
            f"Qty: {qty} yards\n"
            f"Order Value: ₦{gross:,.0f}\n"
            f"You'll receive: ₦{seller_gets:,.0f}\n\n"
            f"⏳ Awaiting buyer payment. Funds will be held in escrow until delivery is confirmed.",
            parse_mode="Markdown"
        )

        # Notify admin
        bot.send_message(ADMIN_ID,
            f"🛒 *NEW ORDER*\n\n"
            f"Ref: `{ref}`\n"
            f"Buyer: {message.from_user.first_name} (`{user_id}`)\n"
            f"Item: {color} {category} x{qty}\n"
            f"Total: ₦{total:,.0f}\n"
            f"OnTabs Fee: ₦{fee:,.0f}\n"
            f"Seller Gets: ₦{seller_gets:,.0f}\n\n"
            f"Status: Awaiting payment receipt 📸",
            parse_mode="Markdown"
        )
        return

    conn.close()

# ─────────────────────────────────────────
#  RECEIPT HANDLER
# ─────────────────────────────────────────
def handle_receipt(message):
    user_id = message.chat.id
    session = get_buyer_session(user_id)

    if not session or session[1] != "AWAITING_RECEIPT":
        bot.reply_to(message, "Thanks for the image! But I'm not expecting a receipt from you right now. Type /start if you need help 😊")
        return

    conn = get_conn()
    c = conn.cursor()

    # Find their latest order
    c.execute("""SELECT reference, seller_id, item_desc, quantity, gross_amount, 
                        seller_receives, product_id
                 FROM orders WHERE buyer_id = ? AND status = 'AWAITING_PAYMENT'
                 ORDER BY created_at DESC LIMIT 1""", (user_id,))
    order = c.fetchone()

    if not order:
        conn.close()
        bot.reply_to(message, "I couldn't find a pending order for you. Type /start to begin again.")
        return

    ref, seller_id, item_desc, qty, gross, seller_gets, p_id = order

    # Get delivery window
    c.execute("SELECT delivery_hrs, shop_name FROM sellers WHERE seller_id = ?", (seller_id,))
    seller_info = c.fetchone()
    delivery_hrs = seller_info[0] if seller_info else 24
    shop_name    = seller_info[1] if seller_info else "the seller"

    release_at = datetime.now() + timedelta(hours=delivery_hrs)

    # Update order — frozen, receipt received, timer set
    c.execute("""UPDATE orders SET status = 'PAID', receipt_url = 'photo_received',
                 paid_at = ?, release_at = ? WHERE reference = ?""",
              (datetime.now().isoformat(), release_at.isoformat(), ref))

    # Reduce stock
    c.execute("UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= 0", (qty, p_id))

    c.execute("UPDATE buyer_sessions SET state = 'START' WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

    bot.reply_to(message,
        f"✅ *Receipt received!*\n\n"
        f"Your payment for `{ref}` is being verified.\n\n"
        f"🔒 Your funds are safely held in escrow.\n"
        f"⏰ If no dispute is raised, funds release to {shop_name} in *{delivery_hrs} hours*.\n\n"
        f"Sit tight — your fabric is on its way! 🎉",
        parse_mode="Markdown"
    )

    # Forward receipt photo to admin
    bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
    bot.send_message(ADMIN_ID,
        f"📸 *Receipt Received*\n\n"
        f"Ref: `{ref}`\n"
        f"Buyer: {message.from_user.first_name} (`{user_id}`)\n"
        f"Item: {item_desc} x{qty}\n"
        f"Amount: ₦{gross:,.0f}\n"
        f"Auto-releases: {release_at.strftime('%d %b %Y, %I:%M %p')}\n\n"
        f"✅ /release {ref} — Release now\n"
        f"🔴 /freeze {ref} — Freeze (dispute)",
        parse_mode="Markdown"
    )

    # Notify seller
    bot.send_message(seller_id,
        f"💛 *Payment Confirmed!*\n\n"
        f"Ref: `{ref}`\n"
        f"Item: {item_desc} x{qty}\n"
        f"Your earnings: *₦{seller_gets:,.0f}* (held in escrow)\n\n"
        f"⏰ Funds release in *{delivery_hrs} hours* after delivery.\n"
        f"Please dispatch the order now! 🚚",
        parse_mode="Markdown"
    )

# ─────────────────────────────────────────
#  AUTO-RELEASE SCHEDULER
# ─────────────────────────────────────────
def auto_release_check():
    """Runs every 30 mins — auto releases orders whose timer has expired."""
    conn = get_conn()
    c = conn.cursor()
    now = datetime.now().isoformat()
    c.execute("""SELECT o.reference, o.buyer_id, o.seller_id, o.item_desc,
                        o.seller_receives, s.shop_name, s.bank_name, s.account_no
                 FROM orders o JOIN sellers s ON o.seller_id = s.seller_id
                 WHERE o.status = 'PAID' AND o.frozen = 1 AND o.release_at <= ?""", (now,))
    due = c.fetchall()

    for order in due:
        ref, buyer_id, seller_id, item_desc, seller_gets, shop, bank, acc = order
        c.execute("UPDATE orders SET frozen = 0, status = 'RELEASED', released_at = ? WHERE reference = ?",
                  (datetime.now().isoformat(), ref))
        conn.commit()

        bot.send_message(ADMIN_ID,
            f"⏰ *Auto-Released*\nRef: `{ref}` — ₦{seller_gets:,.0f} to {shop}",
            parse_mode="Markdown"
        )
        bot.send_message(seller_id,
            f"💚 *Funds Released!*\n\nRef: `{ref}`\nAmount: ₦{seller_gets:,.0f}\nCheck {bank} — {acc} 🎉",
            parse_mode="Markdown"
        )
        bot.send_message(buyer_id,
            f"✅ Your order `{ref}` is complete. Thanks for shopping on OnTabs! 🛍️"
        )

    conn.close()

def auto_repost():
    """Daily 8am price list to linked groups."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT seller_id, shop_name, group_id FROM sellers WHERE group_id IS NOT NULL AND is_approved = 1")
    for seller_id, shop_name, group_id in c.fetchall():
        c.execute("SELECT category, color, price, stock FROM products WHERE seller_id = ?", (seller_id,))
        items = c.fetchall()
        if not items:
            continue
        p_list = "\n".join([
            f"🔹 {r[1]} {r[0]}: ₦{r[2]:,} ({r[3]} yds)" if r[3] >= 0
            else f"🔹 {r[1]} {r[0]}: ₦{r[2]:,}"
            for r in items
        ])
        try:
            bot.send_message(group_id,
                f"🌅 *{shop_name} — Today's Collection*\n\n{p_list}\n\nDM the bot to order 👆",
                parse_mode="Markdown"
            )
        except Exception as e:
            print(f"Repost failed for {shop_name}: {e}")
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
    print("✅ OnTabs Pro v3 — Zero-Trust Escrow System is LIVE.")
    bot.infinity_polling()
