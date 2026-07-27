import os
import telebot
import sqlite3
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

# ─────────────────────────────────────────
#  CONFIG & IDENTITY
# ─────────────────────────────────────────
TOKEN = "YOUR_TOKEN_HERE"  # FIX 1: Token was exposed in plain text — replaced
ADMIN_ID = 123456789
bot = telebot.TeleBot(TOKEN)
DB = "ontabs_pro.db"

# ─────────────────────────────────────────
#  DATABASE (Memory Architecture)
# ─────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS businesses (
        owner_id INTEGER PRIMARY KEY, name TEXT, account TEXT,
        opening TEXT, closing TEXT, group_id INTEGER
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER, category TEXT, color TEXT, price REAL,
        stock INTEGER DEFAULT -1, gender TEXT DEFAULT 'Unisex'
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_sessions (
        user_id INTEGER PRIMARY KEY, current_category TEXT,
        state TEXT, gender_pref TEXT, pending_product_id INTEGER
    )''')
    # FIX 2: orders table added — without this, no purchase record exists after BUY
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER, product_id INTEGER, username TEXT,
        category TEXT, status TEXT DEFAULT 'PENDING',
        created_at TEXT
    )''')
    conn.commit()
    conn.close()

def get_conn():
    return sqlite3.connect(DB)

# ─────────────────────────────────────────
#  FIX 3: /start handler — was completely missing
# ─────────────────────────────────────────
@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message,
        "👋 Welcome! I'm your personal fabric consultant.\n\n"
        "Tell me what you're looking for — e.g.:\n"
        "• _'I need blue lace'_\n"
        "• _'Senator fabric for men'_\n"
        "• _'Chiffon for a bride'_",
        parse_mode="Markdown"
    )

# ─────────────────────────────────────────
#  ADMIN TOOLS (Setup & Escrow)
# ─────────────────────────────────────────
@bot.message_handler(commands=["setbiz"])
def set_business(message):
    """Save Business Name and Bank Details privately."""
    if message.chat.id != ADMIN_ID: return
    try:
        _, parts = message.text.split(maxsplit=1)
        name, acc = [p.strip() for p in parts.split(",", 1)]  # FIX 4: maxsplit=1 prevents crash if account has commas

        conn = get_conn()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO businesses (owner_id, name, account) VALUES (?, ?, ?)",
                  (ADMIN_ID, name, acc))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"🏢 *{name}* setup complete!\nYour payment string is now locked in the vault.",
                     parse_mode="Markdown")
    except:
        bot.reply_to(message, "⚠️ Use format: `/setbiz Shop Name, Bank Name - 0123456789`", parse_mode="Markdown")

# FIX 5: /setgroup command added — group_id was stored in DB but there was no way to set it
@bot.message_handler(commands=["setgroup"])
def set_group(message):
    """Link a Telegram group for auto-reposting. Run this command inside the group."""
    if message.chat.id != ADMIN_ID and message.from_user.id != ADMIN_ID:
        return
    group_id = message.chat.id
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE businesses SET group_id = ? WHERE owner_id = ?", (group_id, ADMIN_ID))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"✅ This group (`{group_id}`) is now linked for daily auto-reposting.", parse_mode="Markdown")

# FIX 6: /addproduct command added — products table existed but had NO way to add items
@bot.message_handler(commands=["addproduct"])
def add_product(message):
    """Add a product to the catalog.
    Format: /addproduct category, color, price, stock, gender
    Example: /addproduct Lace, Royal Blue, 3500, 20, Female
    """
    if message.chat.id != ADMIN_ID: return
    try:
        _, parts = message.text.split(maxsplit=1)
        cat, color, price, stock, gender = [p.strip() for p in parts.split(",")]
        conn = get_conn()
        c = conn.cursor()
        c.execute(
            "INSERT INTO products (owner_id, category, color, price, stock, gender) VALUES (?, ?, ?, ?, ?, ?)",
            (ADMIN_ID, cat.capitalize(), color.capitalize(), float(price), int(stock), gender.capitalize())
        )
        conn.commit()
        conn.close()
        bot.reply_to(message,
            f"✅ Added: *{color.capitalize()} {cat.capitalize()}*\n"
            f"Price: ₦{float(price):,} | Stock: {stock} | Gender: {gender.capitalize()}",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message,
            "⚠️ Format: `/addproduct Lace, Royal Blue, 3500, 20, Female`\n"
            f"Error: {e}", parse_mode="Markdown"
        )

# FIX 7: /stock command added — admin had no way to view current inventory
@bot.message_handler(commands=["stock"])
def view_stock(message):
    """View all products in the catalog."""
    if message.chat.id != ADMIN_ID: return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, category, color, price, stock, gender FROM products WHERE owner_id = ?", (ADMIN_ID,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.reply_to(message, "📭 No products yet. Use /addproduct to add items.")
        return
    lines = ["📦 *Current Stock:*\n"]
    for r in rows:
        stock_label = f"{r[4]} yds" if r[4] >= 0 else "Unlimited"
        lines.append(f"[{r[0]}] {r[2]} {r[1]} — ₦{r[3]:,} | {stock_label} | {r[5]}")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

# ─────────────────────────────────────────
#  ADMIN REPLY HANDLER (Zero-Trust Escrow)
# ─────────────────────────────────────────
@bot.message_handler(func=lambda message: message.reply_to_message and message.chat.id == ADMIN_ID)
def release_payment_details(message):
    """
    If admin replies to a Money Alert with 'pay' → sends invoice to customer.
    If admin replies with anything else → forwards that message directly to customer.
    """
    original_msg = message.reply_to_message.text
    if "💰 MONEY ALERT" not in original_msg:
        return  # FIX 8: was silently processing ALL admin replies — now scoped correctly

    try:
        target_user_id = int(original_msg.split("ID:")[1].split("\n")[0].strip())

        if message.text.lower() == "pay":
            conn = get_conn()
            c = conn.cursor()
            c.execute("SELECT name, account FROM businesses WHERE owner_id = ?", (ADMIN_ID,))
            biz = c.fetchone()
            conn.close()

            if not biz:
                bot.reply_to(message, "❌ No business set up. Use /setbiz first.")
                return

            invoice = (
                f"🛡️ *ZERO-TRUST ESCROW INVOICE*\n"
                f"───────────────────────\n"
                f"Business: *{biz[0]}*\n"
                f"Status: SECURE / PENDING PAYMENT\n\n"
                f"🏦 *PAYMENT INSTRUCTIONS:*\n"
                f"`{biz[1]}`\n\n"
                f"⚠️ _Funds are tracked and held in escrow until delivery is confirmed._\n"
                f"───────────────────────\n"
                f"Kindly upload your receipt screenshot below."
            )
            bot.send_message(target_user_id, invoice, parse_mode="Markdown")
            bot.reply_to(message, "🚀 Invoice released to customer.")

        else:
            bot.send_message(target_user_id, f"💬 *Message from the Boss:*\n\n{message.text}", parse_mode="Markdown")
            bot.reply_to(message, "✅ Message forwarded to customer.")

    except Exception as e:
        bot.reply_to(message, f"⚠️ Error: {e}")

# ─────────────────────────────────────────
#  CONSULTANT BRAIN (Sales Funnel)
# ─────────────────────────────────────────
@bot.message_handler(func=lambda message: True)
def ontabs_consultant(message):
    user_id = message.chat.id
    text = message.text.strip().lower()
    if text.startswith('/'): return

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT current_category, state, gender_pref, pending_product_id FROM user_sessions WHERE user_id = ?", (user_id,))
    session = c.fetchone()
    # session: [0]current_category [1]state [2]gender_pref [3]pending_product_id

    # 1. Gender Recognition
    male_keys   = ["man", "male", "men", "groom", "atiku", "senator"]
    female_keys = ["woman", "female", "lace", "chiffon", "silk", "bride"]
    detected_gender = (
        "Male"   if any(w in text for w in male_keys) else
        "Female" if any(w in text for w in female_keys) else
        "Unisex"
    )

    # 2. Category Detection — now pulled from DB instead of hardcoded list
    # FIX 9: hardcoded category list meant new product types were invisible to the bot
    c.execute("SELECT DISTINCT category FROM products WHERE owner_id = ?", (ADMIN_ID,))
    db_categories = [row[0].lower() for row in c.fetchall()]
    matched_cat = next((cat for cat in db_categories if cat in text), None)

    # ── LEVEL 1: Category Trigger ──
    if matched_cat and (not session or session[1] in ("START", None)):
        c.execute(
            "INSERT OR REPLACE INTO user_sessions (user_id, current_category, state, gender_pref) VALUES (?, ?, ?, ?)",
            (user_id, matched_cat.capitalize(), "WAITING_FOR_COLOR", detected_gender)
        )
        bot.reply_to(message,
            f"✨ High-quality *{matched_cat.capitalize()}* for *{detected_gender}s*!\n\nWhich color are you looking for?",
            parse_mode="Markdown"
        )

    # ── LEVEL 2: Color → Stock & Price ──
    elif session and session[1] == "WAITING_FOR_COLOR":
        category, gender = session[0], session[2]
        c.execute(
            """SELECT id, color, price, stock FROM products
               WHERE category = ? AND color LIKE ?
               AND (gender = ? OR gender = 'Unisex') COLLATE NOCASE""",
            (category, f"%{text}%", gender)
        )
        product = c.fetchone()

        if product:
            p_id, color, price, stock = product
            stock_label = f"{stock} yards available" if stock >= 0 else "In Stock"
            c.execute(
                "UPDATE user_sessions SET state = 'NEGOTIATING', pending_product_id = ? WHERE user_id = ?",
                (p_id, user_id)
            )
            # FIX 10: parse_mode was missing — bold text showed as raw asterisks
            bot.reply_to(message,
                f"✅ *{color} {category}*\nPrice: ₦{price:,} per yard\n{stock_label}\n\nType *BUY* to proceed to payment.",
                parse_mode="Markdown"
            )
        else:
            bot.reply_to(message, f"I don't see that color in stock. I've alerted the Boss to check the warehouse!")
            bot.send_message(ADMIN_ID,
                f"🚨 *WAREHOUSE ALERT*\nID: `{user_id}`\nUser wants: _{text} {category}_",
                parse_mode="Markdown"
            )

    # ── LEVEL 3: BUY → Money Alert ──
    elif "buy" in text and session and session[1] == "NEGOTIATING":
        # FIX 11: order now saved to DB so there's a record — was fire-and-forget before
        p_id = session[3]
        c.execute(
            "INSERT INTO orders (user_id, product_id, username, category, status, created_at) VALUES (?, ?, ?, ?, 'PENDING', ?)",
            (user_id, p_id, message.from_user.first_name, session[0], datetime.now().isoformat())
        )
        bot.reply_to(message, "Signaling the Boss for payment verification. Stand by... ⏳")
        bot.send_message(
            ADMIN_ID,
            f"💰 *MONEY ALERT*\n"
            f"ID: `{user_id}`\n"
            f"User: {message.from_user.first_name}\n"
            f"Wants: *{session[0]}* (Product ID: {p_id})\n\n"
            f"👉 Reply *pay* to release invoice, or type a custom message to send directly.",
            parse_mode="Markdown"
        )
        # Reset session after order placed
        c.execute("UPDATE user_sessions SET state = 'START' WHERE user_id = ?", (user_id,))

    conn.commit()
    conn.close()

# ─────────────────────────────────────────
#  AUTO-PILOT SCHEDULER (Daily Repost)
# ─────────────────────────────────────────
def auto_repost():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT owner_id, name, account, group_id FROM businesses WHERE group_id IS NOT NULL")
    for row in c.fetchall():
        owner_id, name, account, group_id = row
        c.execute("SELECT category, color, price, stock FROM products WHERE owner_id = ?", (owner_id,))
        items = c.fetchall()
        if not items:
            continue
        # FIX 12: stock now shown in repost — customers had no way to know availability
        p_list = "\n".join([
            f"🔹 {r[1]} {r[0]}: ₦{r[2]:,} ({r[3]} yds)" if r[3] >= 0
            else f"🔹 {r[1]} {r[0]}: ₦{r[2]:,}"
            for r in items
        ])
        try:
            bot.send_message(group_id, f"🛒 *{name} — TODAY'S PRICE LIST*\n\n{p_list}", parse_mode="Markdown")
        except Exception as e:
            print(f"Repost failed for group {group_id}: {e}")
    conn.close()

# ─────────────────────────────────────────
#  LAUNCH
# ─────────────────────────────────────────
if __name__ == "__main__":
    init_db()
    scheduler = BackgroundScheduler()
    scheduler.add_job(auto_repost, 'cron', hour=8, minute=0)
    scheduler.start()
    print("✅ ONTABS PRO: Zero-Trust Integrated System is live.")
    bot.infinity_polling()
