import os
import re
import random
import sqlite3
from datetime import datetime, timedelta, timezone

def utcnow():
    return datetime.now(timezone.utc).isoformat()
from apscheduler.schedulers.background import BackgroundScheduler
import telebot
from telebot.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    ReplyKeyboardRemove, InlineKeyboardMarkup, InlineKeyboardButton
)

# ═══════════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════════
TOKEN    = "8725049105:AAH-owSwsFoM6mUhFumbkJXSAfpG8YO2Ou0"
ADMIN_ID = 8691777338

ESCROW_BANK    = "GTBank"
ESCROW_NAME    = "OnTabs Business Inc"
ESCROW_ACCOUNT = "0123456789"
ONTABS_FEE_PCT = 0.005  # 0.5%

MAIN_DB = "ontabs_pro.db"
OIL_DB  = "oilcompany.db"

bot = telebot.TeleBot("8725049105:AAH-owSwsFoM6mUhFumbkJXSAfpG8YO2Ou0")

# ═══════════════════════════════════════════════════════
#  TERMS & CONDITIONS
# ═══════════════════════════════════════════════════════
BUYER_TC = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  _OnTabs Marketplace — Buyer Agreement_
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

By proceeding, you acknowledge and agree:

1. *Payment* — All payments are held in escrow by OnTabs until delivery is confirmed or the release window expires. Funds are non-refundable once released to the seller.

2. *Receipts* — Submitting a false or edited payment receipt is fraud. OnTabs reserves the right to blacklist and report any such account.

3. *Delivery* — Delivery timelines are set by each seller. OnTabs is not liable for delays caused by dispatch riders or third parties.

4. *Disputes* — All disputes must be raised within 24 hours of the stated delivery window. Contact admin with your order reference.

5. *Identity* — You agree that your Telegram identity, phone number, and delivery address may be shared with the seller for the purpose of fulfilling your order. This information is not sold or shared beyond that.

6. *Conduct* — Harassment of sellers, false claims, or abuse of the escrow system will result in permanent removal.

7. *Tabs* — Unpaid orders or abandoned carts are logged. Repeated non-payment will result in restricted access.

_OnTabs exists to protect both sides of every transaction. We are the grey in the room — calm, firm, and watching._

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

SELLER_TC = """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  _OnTabs Marketplace — Seller Agreement_
━━━━━━━━━━━━━━━━━━━━━━━━━━━━

By registering your shop, you agree:

1. *Escrow* — Payments from buyers are held by OnTabs and released after your set delivery window expires. Early release requires admin approval.

2. *Fulfilment* — Once a buyer pays, you are obligated to dispatch within your stated delivery window. Failure to do so may result in a refund to the buyer and a strike on your account.

3. *Products* — All listings must be accurate. Misleading descriptions, fake stock, or price manipulation will result in immediate suspension.

4. *Bank Details* — You are responsible for providing correct account details. OnTabs is not liable for funds sent to a wrong account you provided.

5. *Commission* — OnTabs deducts 0.5% of each transaction as a service fee before releasing funds to you.

6. *Conduct* — Sellers who ghost buyers, manipulate reviews, or coordinate fraud will be permanently banned and reported.

7. *Verification* — OnTabs admin reserves the right to verify your identity, shop, and products at any time.

_Your shop runs on trust. OnTabs holds the line for everyone — including you._

━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

# ═══════════════════════════════════════════════════════
#  DATABASE INIT
# ═══════════════════════════════════════════════════════
def init_main_db():
    conn = sqlite3.connect(MAIN_DB)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS sellers (
        seller_id      INTEGER PRIMARY KEY,
        shop_name      TEXT,
        industry       TEXT DEFAULT 'Fabric',
        bank_name      TEXT,
        account_no     TEXT,
        account_name   TEXT,
        delivery_hrs   INTEGER DEFAULT 24,
        is_approved    INTEGER DEFAULT 0,
        tc_agreed      INTEGER DEFAULT 0,
        tc_agreed_at   TEXT,
        joined_at      TEXT,
        total_earned   REAL DEFAULT 0,
        total_paid_out REAL DEFAULT 0,
        bio            TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS seller_sessions (
        seller_id    INTEGER PRIMARY KEY,
        state        TEXT,
        industry     TEXT,
        shop_name    TEXT,
        bank_name    TEXT,
        account_no   TEXT,
        account_name TEXT,
        delivery_hrs INTEGER,
        bio          TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER,
        db_source TEXT DEFAULT 'main',
        category  TEXT,
        name      TEXT,
        color     TEXT,
        price     REAL,
        stock     INTEGER DEFAULT -1,
        unit      TEXT DEFAULT 'yards',
        gender    TEXT DEFAULT 'Unisex'
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS buyer_profiles (
        user_id      INTEGER PRIMARY KEY,
        full_name    TEXT,
        phone        TEXT,
        address      TEXT,
        tc_agreed    INTEGER DEFAULT 0,
        tc_agreed_at TEXT,
        joined_at    TEXT,
        total_orders INTEGER DEFAULT 0,
        total_spent  REAL DEFAULT 0,
        is_blacklist INTEGER DEFAULT 0,
        is_approved  INTEGER DEFAULT 0,
        approved_at  TEXT,
        approved_by  INTEGER
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS buyer_sessions (
        user_id            INTEGER PRIMARY KEY,
        state              TEXT,
        industry           TEXT DEFAULT 'Fabric',
        current_category   TEXT,
        current_seller_id  INTEGER,
        gender_pref        TEXT,
        pending_product_id INTEGER,
        quantity           INTEGER DEFAULT 0,
        temp_address       TEXT,
        temp_phone         TEXT,
        order_count        INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        reference        TEXT UNIQUE,
        db_source        TEXT DEFAULT 'main',
        buyer_id         INTEGER,
        seller_id        INTEGER,
        product_id       INTEGER,
        buyer_name       TEXT,
        buyer_phone      TEXT,
        buyer_address    TEXT,
        buyer_landmark   TEXT,
        item_desc        TEXT,
        quantity         INTEGER,
        unit             TEXT,
        unit_price       REAL,
        gross_amount     REAL,
        ontabs_fee       REAL,
        seller_receives  REAL,
        status           TEXT DEFAULT 'AWAITING_PAYMENT',
        frozen           INTEGER DEFAULT 0,
        receipt_msg_id   INTEGER,
        created_at       TEXT,
        paid_at          TEXT,
        release_at       TEXT,
        released_at      TEXT,
        buy_attempt      INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS tc_log (
        id         INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id    INTEGER,
        role       TEXT,
        agreed_at  TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS announcement_config (
        id        INTEGER PRIMARY KEY CHECK (id = 1),
        times_day INTEGER DEFAULT 5,
        group_id  INTEGER
    )''')

    conn.commit()
    conn.close()


def init_oil_db():
    conn = sqlite3.connect(OIL_DB)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS oil_sellers (
        seller_id      INTEGER PRIMARY KEY,
        shop_name      TEXT,
        company_name   TEXT,
        bank_name      TEXT,
        account_no     TEXT,
        account_name   TEXT,
        delivery_hrs   INTEGER DEFAULT 48,
        is_approved    INTEGER DEFAULT 0,
        tc_agreed      INTEGER DEFAULT 0,
        tc_agreed_at   TEXT,
        joined_at      TEXT,
        total_earned   REAL DEFAULT 0,
        total_paid_out REAL DEFAULT 0,
        bio            TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS oil_products (
        id        INTEGER PRIMARY KEY AUTOINCREMENT,
        seller_id INTEGER,
        name      TEXT,
        price     REAL,
        stock     INTEGER DEFAULT -1,
        unit      TEXT DEFAULT 'Liters'
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS oil_seller_sessions (
        seller_id    INTEGER PRIMARY KEY,
        state        TEXT,
        shop_name    TEXT,
        company_name TEXT,
        bank_name    TEXT,
        account_no   TEXT,
        account_name TEXT,
        delivery_hrs INTEGER,
        bio          TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS oil_orders (
        id               INTEGER PRIMARY KEY AUTOINCREMENT,
        reference        TEXT UNIQUE,
        buyer_id         INTEGER,
        seller_id        INTEGER,
        product_id       INTEGER,
        buyer_name       TEXT,
        buyer_phone      TEXT,
        buyer_address    TEXT,
        buyer_landmark   TEXT,
        item_desc        TEXT,
        quantity         INTEGER,
        unit             TEXT,
        unit_price       REAL,
        gross_amount     REAL,
        ontabs_fee       REAL,
        seller_receives  REAL,
        status           TEXT DEFAULT 'AWAITING_PAYMENT',
        frozen           INTEGER DEFAULT 0,
        receipt_msg_id   INTEGER,
        created_at       TEXT,
        paid_at          TEXT,
        release_at       TEXT,
        released_at      TEXT
    )''')

    conn.commit()
    conn.close()


def get_conn(db=MAIN_DB):
    return sqlite3.connect(db)

# ═══════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════
def migrate_buyer_profiles():
    """Add new columns to existing buyer_profiles table safely."""
    conn = get_conn()
    c = conn.cursor()
    columns = [r[1] for r in c.execute("PRAGMA table_info(buyer_profiles)")]
    if "is_approved" not in columns:
        c.execute("ALTER TABLE buyer_profiles ADD COLUMN is_approved INTEGER DEFAULT 0")
    if "approved_at" not in columns:
        c.execute("ALTER TABLE buyer_profiles ADD COLUMN approved_at TEXT")
    if "approved_by" not in columns:
        c.execute("ALTER TABLE buyer_profiles ADD COLUMN approved_by INTEGER")
    conn.commit()
    conn.close()

def gen_reference(prefix="OT"):
    conn = get_conn()
    c = conn.cursor()
    while True:
        ref = f"{prefix}-{''.join([str(random.randint(0,9)) for _ in range(9)])}"
        c.execute("SELECT id FROM orders WHERE reference = ?", (ref,))
        if not c.fetchone():
            conn.close()
            return ref

def log_event(event_type, details):
    with open("marketplace_logs.txt", "a", encoding="utf-8") as log:
        log.write(f"[{utcnow()}] {event_type}: {details}\n")

def is_blacklisted(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT is_blacklist FROM buyer_profiles WHERE user_id = ?", (user_id,))
    r = c.fetchone()
    conn.close()
    return r and r[0] == 1

def is_buyer_approved(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT is_approved FROM buyer_profiles WHERE user_id = ?", (user_id,))
    r = c.fetchone()
    conn.close()
    return r and r[0] == 1

def buyer_agreed_tc(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT tc_agreed FROM buyer_profiles WHERE user_id = ?", (user_id,))
    r = c.fetchone()
    conn.close()
    return r and r[0] == 1

def seller_agreed_tc(user_id, oil=False):
    db  = OIL_DB if oil else MAIN_DB
    tbl = "oil_sellers" if oil else "sellers"
    conn = get_conn(db)
    c = conn.cursor()
    c.execute(f"SELECT tc_agreed FROM {tbl} WHERE seller_id = ?", (user_id,))
    r = c.fetchone()
    conn.close()
    return r and r[0] == 1

def is_seller(user_id, oil=False):
    db  = OIL_DB if oil else MAIN_DB
    tbl = "oil_sellers" if oil else "sellers"
    conn = get_conn(db)
    c = conn.cursor()
    c.execute(f"SELECT seller_id FROM {tbl} WHERE seller_id = ? AND is_approved = 1", (user_id,))
    r = c.fetchone()
    conn.close()
    return r is not None

def is_pending_seller(user_id, oil=False):
    db  = OIL_DB if oil else MAIN_DB
    tbl = "oil_seller_sessions" if oil else "seller_sessions"
    conn = get_conn(db)
    c = conn.cursor()
    c.execute(f"SELECT state FROM {tbl} WHERE seller_id = ?", (user_id,))
    r = c.fetchone()
    conn.close()
    return r is not None

def get_session(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT state, current_category, gender_pref,
                 pending_product_id, quantity, current_seller_id,
                 industry, temp_address, temp_phone
                 FROM buyer_sessions WHERE user_id = ?""", (user_id,))
    r = c.fetchone()
    conn.close()
    return r

def set_session_state(user_id, state):
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE buyer_sessions SET state = ? WHERE user_id = ?", (state, user_id))
    conn.commit()
    conn.close()

def has_pending_order(user_id):
    """Prevent duplicate active orders."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT id FROM orders WHERE buyer_id = ?
                 AND status IN ('AWAITING_PAYMENT') LIMIT 1""", (user_id,))
    r = c.fetchone()
    conn.close()
    if r:
        return True
    conn2 = get_conn(OIL_DB)
    c2 = conn2.cursor()
    c2.execute("""SELECT id FROM oil_orders WHERE buyer_id = ?
                  AND status IN ('AWAITING_PAYMENT') LIMIT 1""", (user_id,))
    r2 = c2.fetchone()
    conn2.close()
    return r2 is not None

def gender_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row(KeyboardButton("👗 For a Lady"), KeyboardButton("👔 For a Man"))
    kb.row(KeyboardButton("🎁 It's a Gift"))
    return kb

def industry_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row(KeyboardButton("🫙 Oil"), KeyboardButton("🧵 Fabric & Fashion"))
    kb.row(KeyboardButton("🛠️ I offer Services"))
    kb.row(KeyboardButton("🔙 Back"))
    return kb

def main_menu_keyboard():
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row(KeyboardButton("🛍️ I want to buy"), KeyboardButton("🏪 I want to sell"))
    return kb

# ═══════════════════════════════════════════════════════
#  /start
# ═══════════════════════════════════════════════════════

@bot.message_handler(commands=['reset'])
def cmd_reset(message):
    user_id = message.chat.id
    
    # Delete from all seller tables
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM sellers WHERE seller_id = ?", (user_id,))
    c.execute("DELETE FROM seller_sessions WHERE seller_id = ?", (user_id,))
    c.execute("DELETE FROM service_seller_sessions WHERE seller_id = ?", (user_id,))
    conn.commit()
    conn.close()
    
    conn2 = get_conn(OIL_DB)
    c2 = conn2.cursor()
    c2.execute("DELETE FROM oil_sellers WHERE seller_id = ?", (user_id,))
    c2.execute("DELETE FROM oil_seller_sessions WHERE seller_id = ?", (user_id,))
    conn2.commit()
    conn2.close()
    
    bot.reply_to(message, "Account reset! You can now register as buyer or seller again.")

@bot.message_handler(commands=['start'])
def cmd_start(message):
    user_id = message.chat.id
    name    = message.from_user.first_name

    # Auto-approve admin as buyer too
    if user_id == ADMIN_ID:
        conn = get_conn()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO buyer_profiles (user_id, joined_at, is_approved) VALUES (?, ?, 1)",
                  (user_id, utcnow()))
        conn.commit()
        conn.close()

    if user_id == ADMIN_ID:
        bot.reply_to(message,
            "👑 *OnTabs Admin Panel*\n\n"
            "━━━━━━━━━━━━━━━━\n"
            "*Sellers*\n"
            "/approve [id] — Approve seller\n"
            "/approvebuyer [id] — Approve buyer\n"
            "/pendingbuyers — Buyers awaiting approval\n"
            "/selleraccounts — All seller bank details\n"
            "/unpaid — Sellers awaiting payout\n"
            "/sellers — All sellers list\n\n"
            "*Orders*\n"
            "/orders — Recent orders\n"
            "/release [ref] — Release funds\n"
            "/freeze [ref] — Freeze order\n"
            "/suspicious — Flag suspicious receipts\n\n"
            "*Buyers*\n"
            "/buyertabs — Buyers with open orders\n"
            "/blacklist [id] — Blacklist buyer\n\n"
            "*Announcements*\n"
            "/setannounce [count] [group_id] — Set daily posts\n"
            "/announce now — Post immediately\n\n"
            "*Debug*\n"
            "/debug — System status",
            parse_mode="Markdown"
        )
        return

    if is_blacklisted(user_id):
        bot.reply_to(message, "🚫 Your account has been restricted. Contact support.")
        return

    if is_seller(user_id) or is_seller(user_id, oil=True):
        seller_dashboard(message)
        return

    if is_pending_seller(user_id) or is_pending_seller(user_id, oil=True):
        bot.reply_to(message, "👋 You're still registering! Let's continue 😊")
        handle_seller_reg(message)
        return

    # Register buyer profile if new
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO buyer_profiles (user_id, joined_at) VALUES (?, ?)",
              (user_id, utcnow()))
    conn.commit()
    conn.close()

    # Gate on buyer approval
    if not is_buyer_approved(user_id):
        bot.reply_to(message,
            f"Hey *{name}!* 👋\n\n"
            f"Welcome to *OnTabs* — Nigeria's zero-trust marketplace 🇳🇬\n\n"
            f"Your account is pending admin approval. You'll be notified once approved! 🕐",
            parse_mode="Markdown"
        )
        safe_buyer_name = (name or "").replace("*","").replace("`","").replace("_","")
        bot.send_message(ADMIN_ID,
            f"👤 *New Buyer Pending Approval*\n\n"
            f"Name: {safe_buyer_name}\nID: `{user_id}`\n\n"
            f"/approvebuyer {user_id}",
            parse_mode="Markdown"
        )
        return

    bot.reply_to(message,
        f"Hey *{name}!* 👋\n\n"
        f"Welcome to *OnTabs* — Nigeria's zero-trust marketplace 🇳🇬\n\n"
        f"What brings you here today?",
        reply_markup=main_menu_keyboard(),
        parse_mode="Markdown"
    )

# ═══════════════════════════════════════════════════════
#  SELLER DASHBOARD
# ═══════════════════════════════════════════════════════
def seller_dashboard(message):
    user_id = message.chat.id

    oil = is_seller(user_id, oil=True)
    db  = OIL_DB if oil else MAIN_DB
    tbl_s = "oil_sellers" if oil else "sellers"
    tbl_o = "oil_orders"  if oil else "orders"

    conn = get_conn(db)
    c = conn.cursor()
    c.execute(f"SELECT shop_name, bank_name, account_no, account_name, total_earned, total_paid_out FROM {tbl_s} WHERE seller_id = ?", (user_id,))
    seller = c.fetchone()
    c.execute(f"SELECT COUNT(*) FROM {tbl_o} WHERE seller_id = ? AND status = 'AWAITING_PAYMENT'", (user_id,))
    pending = c.fetchone()[0]
    c.execute(f"SELECT COUNT(*) FROM {tbl_o} WHERE seller_id = ? AND status = 'PAID'", (user_id,))
    in_escrow = c.fetchone()[0]
    c.execute(f"SELECT COALESCE(SUM(seller_receives),0) FROM {tbl_o} WHERE seller_id = ? AND status = 'RELEASED'", (user_id,))
    earned = c.fetchone()[0]
    c.execute(f"SELECT COALESCE(SUM(seller_receives),0) FROM {tbl_o} WHERE seller_id = ? AND status = 'RELEASED' AND released_at IS NOT NULL", (user_id,))
    paid_out = c.fetchone()[0]
    owed = earned - paid_out
    conn.close()

    label = "🫙 Oil" if oil else "🧵 Fabric"

    bot.send_message(user_id,
        f"👋 Welcome back, *{seller[0]}!*\n"
        f"_{label} Seller_\n\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🔴 Awaiting Payment: *{pending}*\n"
        f"🟡 In Escrow: *{in_escrow}*\n"
        f"✅ Total Earned: *₦{earned:,.0f}*\n"
        f"💸 Paid Out: *₦{paid_out:,.0f}*\n"
        f"⏳ Still Owed: *₦{owed:,.0f}*\n"
        f"━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🏦 *{seller[1]}* — `{seller[2]}` ({seller[3]})\n\n"
        f"/addproduct — Add item\n"
        f"/updatestock — Update stock\n"
        f"/mystock — View catalog\n"
        f"/myorders — View orders\n"
        f"/myprofile — Your shop profile\n",
        parse_mode="Markdown"
    )

# ═══════════════════════════════════════════════════════
#  BUYER PROFILE
# ═══════════════════════════════════════════════════════
@bot.message_handler(commands=['myprofile'])
def cmd_myprofile(message):
    user_id = message.chat.id

    if is_seller(user_id) or is_seller(user_id, oil=True):
        oil = is_seller(user_id, oil=True)
        db  = OIL_DB if oil else MAIN_DB
        tbl = "oil_sellers" if oil else "sellers"
        conn = get_conn(db)
        c = conn.cursor()
        c.execute(f"SELECT shop_name, bank_name, account_no, account_name, delivery_hrs, bio, joined_at FROM {tbl} WHERE seller_id = ?", (user_id,))
        s = c.fetchone()
        conn.close()
        bot.reply_to(message,
            f"🏪 *Shop Profile*\n\n"
            f"Name: *{s[0]}*\n"
            f"Bank: {s[1]} — `{s[2]}`\n"
            f"Account Name: {s[3]}\n"
            f"Delivery Window: {s[4]}hrs\n"
            f"Bio: _{s[5] or 'Not set'}_\n"
            f"Joined: {s[6][:10] if s[6] else 'N/A'}",
            parse_mode="Markdown"
        )
        return

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT full_name, phone, address, tc_agreed, joined_at, total_orders, total_spent, is_approved FROM buyer_profiles WHERE user_id = ?", (user_id,))
    b = c.fetchone()
    conn.close()
    if not b:
        bot.reply_to(message, "No profile yet. Type /start to begin.")
        return
    bot.reply_to(message,
        f"👤 *Your Profile*\n\n"
        f"Name: *{b[0] or 'Not set'}*\n"
        f"Phone: {b[1] or 'Not set'}\n"
        f"Address: {b[2] or 'Not set'}\n"
        f"T&C: {'✅ Agreed' if b[3] else '❌ Not agreed'}\n"
        f"Status: {'✅ Approved' if b[7] else '⏳ Pending Approval'}\n"
        f"Joined: {b[4][:10] if b[4] else 'N/A'}\n"
        f"Orders: {b[5] or 0}\n"
        f"Total Spent: ₦{b[6] or 0:,.0f}",
        parse_mode="Markdown"
    )

# ═══════════════════════════════════════════════════════
#  SELLER REGISTRATION — FABRIC
# ═══════════════════════════════════════════════════════


def start_service_seller_reg(message):
    user_id = message.chat.id
    name = message.from_user.first_name or "Partner"

    if is_seller(user_id):
        bot.reply_to(message, "You are already registered as a Product Seller.")
        return

    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO service_seller_sessions (seller_id, state) VALUES (?, 'WAITING_BUSINESS_NAME')", (user_id,))
    conn.commit()
    conn.close()

    bot.send_message(user_id,
        f"OnTabs Service Provider Registration\n\n"
        f"Welcome {name}!\n\n"
        f"Please reply with your official Business or Freelance Name:"
    )


def start_service_buyer_flow(message):
    user_id = message.chat.id
    
    # Show service categories
    kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
    kb.row(KeyboardButton("💇 Barbering"), KeyboardButton("🍽️ Catering"))
    kb.row(KeyboardButton("✂️ Tailoring"), KeyboardButton("🔨 Carpentry"))
    kb.row(KeyboardButton("🎨 Graphic Design"), KeyboardButton("📸 Photography"))
    kb.row(KeyboardButton("🔙 Back"))
    
    bot.send_message(user_id,
        "What service are you looking for? 👇",
        reply_markup=kb
    )
    
    # Set buyer state to browsing services
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO buyer_sessions (user_id, state, industry) VALUES (?, 'BROWSING_SERVICES', 'Services')", (user_id,))
    conn.commit()
    conn.close()

def handle_service_seller_reg(message):
    user_id = message.chat.id
    text = message.text.strip() if message.text else ""

    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT state FROM service_seller_sessions WHERE seller_id = ?", (user_id,))
    sess = c.fetchone()
    conn.close()

    if not sess:
        return

    state = sess[0]

    if state == "WAITING_BUSINESS_NAME":
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE service_seller_sessions SET business_name = ?, state = 'WAITING_SKILL' WHERE seller_id = ?", (text, user_id))
        conn.commit()
        conn.close()
        bot.send_message(user_id, "Business name saved!\n\nWhat service do you offer?\n(e.g., Barbering, Catering, Tailoring):")
        return

    if state == "WAITING_SKILL":
        if len(text) < 3:
            bot.send_message(user_id, "Please enter a valid skill description:")
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE service_seller_sessions SET skill_category = ?, state = 'WAITING_DELIVERY_DAYS' WHERE seller_id = ?", (text, user_id))
        conn.commit()
        conn.close()
        bot.send_message(user_id, "Skill saved!\n\nHow many days to complete a standard job? (e.g., 3):")
        return

    if state == "WAITING_DELIVERY_DAYS":
        if not text.isdigit():
            bot.send_message(user_id, "Please enter a valid number of days:")
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE service_seller_sessions SET delivery_hrs = ?, state = 'SERVICE_TC_PENDING' WHERE seller_id = ?", (int(text), user_id))
        conn.commit()
        conn.close()
        bot.send_message(user_id, "OnTabs Service Agreement:\n\n1. Buyers pay 100% upfront into escrow.\n2. 30% released to you immediately.\n3. 70% released after delivery confirmed.\n\nType AGREE to continue.")
        return

    if state == "SERVICE_TC_PENDING":
        if text.lower() != "agree":
            bot.send_message(user_id, "Please type AGREE to accept and continue:")
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE service_seller_sessions SET state = 'ASK_BANK_NAME' WHERE seller_id = ?", (user_id,))
        conn.commit()
        conn.close()
        bot.send_message(user_id, "Agreement accepted!\n\nWhich bank will you receive payments to?")
        return

    if state == "ASK_BANK_NAME":
        if len(text) < 2:
            bot.send_message(user_id, "Please enter a valid bank name:")
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE service_seller_sessions SET bank_name = ?, state = 'ASK_ACCOUNT_NO' WHERE seller_id = ?", (text, user_id))
        conn.commit()
        conn.close()
        bot.send_message(user_id, f"Got it — {text}\n\nWhat is your 10-digit account number?")
        return

    if state == "ASK_ACCOUNT_NO":
        if not text.isdigit() or len(text) != 10:
            bot.send_message(user_id, "Please enter a valid 10-digit account number:")
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT business_name, skill_category, bank_name FROM service_seller_sessions WHERE seller_id = ?", (user_id,))
        info = c.fetchone()
        c.execute("UPDATE service_seller_sessions SET account_no = ?, state = 'PENDING_APPROVAL' WHERE seller_id = ?", (text, user_id))
        conn.commit()
        conn.close()
        c2 = get_conn()
        cur = c2.cursor()
        cur.execute("UPDATE service_seller_sessions SET state = 'AWAITING_SUBSCRIPTION_RECEIPT' WHERE seller_id = ?", (user_id,))
        c2.commit()
        c2.close()
        bot.send_message(user_id,
            "Almost there!\n\n"
            "To activate your OnTabs Service Provider account, pay the monthly subscription fee:\n\n"
            "Amount: N12,500\n"
            f"Bank: {ESCROW_BANK}\n"
            f"Account: {ESCROW_ACCOUNT}\n"
            f"Name: {ESCROW_NAME}\n\n"
            "Send your payment receipt here to complete registration."
        )
        if info:
            bot.send_message(ADMIN_ID,
                f"New Service Seller\n\n"
                f"ID: {user_id}\n"
                f"Business: {info[0]}\n"
                f"Skill: {info[1]}\n"
                f"Bank: {info[2]} — {text}\n\n"
                f"/approve {user_id}"
            )
        return

def start_seller_reg(message, industry="Fabric"):
    user_id = message.chat.id
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO seller_sessions (seller_id, state, industry) VALUES (?, 'ASK_SHOP_NAME', ?)",
              (user_id, industry))
    conn.commit()
    conn.close()
    bot.send_message(user_id,
        f"🏪 *Setting up your OnTabs {industry} Shop!*\n\n"
        f"First, read and accept the Seller Agreement:\n"
        f"{SELLER_TC}\n\n"
        f"Type *AGREE* to accept and continue.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )
    # Temporarily set state to TC_PENDING
    conn2 = get_conn()
    c2 = conn2.cursor()
    c2.execute("UPDATE seller_sessions SET state = 'TC_PENDING' WHERE seller_id = ?", (user_id,))
    conn2.commit()
    conn2.close()

def start_oil_seller_reg(message):
    user_id = message.chat.id
    conn = get_conn(OIL_DB)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO oil_seller_sessions (seller_id, state) VALUES (?, 'TC_PENDING')", (user_id,))
    conn.commit()
    conn.close()
    bot.send_message(user_id,
        f"🫙 *Setting up your OnTabs Oil Shop!*\n\n"
        f"First, read and accept the Seller Agreement:\n"
        f"{SELLER_TC}\n\n"
        f"Type *AGREE* to accept and continue.",
        parse_mode="Markdown",
        reply_markup=ReplyKeyboardRemove()
    )

def handle_seller_reg(message, oil=False):
    user_id = message.chat.id
    text    = message.text.strip() if message.text else ""
    lower   = text.lower()
    db      = OIL_DB if oil else MAIN_DB
    tbl     = "oil_seller_sessions" if oil else "seller_sessions"

    conn = get_conn(db)
    c = conn.cursor()
    c.execute(f"SELECT state, shop_name, bank_name, account_no, account_name, delivery_hrs FROM {tbl} WHERE seller_id = ?", (user_id,))
    sess = c.fetchone()
    conn.close()

    if not sess:
        return

    state = sess[0]

    if state == "TC_PENDING":
        if lower != "agree":
            bot.send_message(user_id, "Please type *AGREE* to accept the terms and continue.", parse_mode="Markdown")
            return
        conn2 = get_conn(db)
        c2 = conn2.cursor()
        c2.execute(f"UPDATE {tbl} SET state = 'ASK_SHOP_NAME' WHERE seller_id = ?", (user_id,))
        conn2.commit()
        conn2.close()
        # Log TC
        log_conn = get_conn()
        lc = log_conn.cursor()
        lc.execute("INSERT INTO tc_log (user_id, role, agreed_at) VALUES (?, 'seller', ?)",
                   (user_id, utcnow()))
        log_conn.commit()
        log_conn.close()
        bot.send_message(user_id, "✅ Agreement accepted.\n\nWhat's the name of your shop? 👇", parse_mode="Markdown")
        return

    conn3 = get_conn(db)
    c3 = conn3.cursor()

    if state == "ASK_SHOP_NAME":
        c3.execute(f"UPDATE {tbl} SET shop_name = ?, state = 'ASK_COMPANY_NAME' WHERE seller_id = ?", (text, user_id))
        conn3.commit()
        conn3.close()
        label = "company/brand name" if oil else "bank name (e.g. GTBank, Opay)"
        bot.send_message(user_id,
            f"Love it! *{text}* 🔥\n\n{'What is your registered company or brand name?' if oil else 'Which bank will you receive payments to?'}\n",
            parse_mode="Markdown")
        return

    if state == "ASK_COMPANY_NAME":
        # For oil this stores company name; for fabric it stores bank name
        field = "company_name" if oil else "bank_name"
        c3.execute(f"UPDATE {tbl} SET {field} = ?, state = 'ASK_BANK_NAME' WHERE seller_id = ?", (text, user_id))
        conn3.commit()
        conn3.close()
        prompt = "Which bank will you receive payments to?\n_(e.g. GTBank, Opay, Palmpay)_" if oil else "What is your account number?"
        next_state_override = None
        if oil:
            bot.send_message(user_id, prompt, parse_mode="Markdown")
        else:
            # Fabric skips company name — reuse ASK_COMPANY_NAME as ASK_BANK_NAME
            bot.send_message(user_id, "What is your account number? 👇", parse_mode="Markdown")
            c3_fix = get_conn(db)
            cf = c3_fix.cursor()
            cf.execute(f"UPDATE {tbl} SET bank_name = ?, state = 'ASK_ACCOUNT_NO' WHERE seller_id = ?", (text, user_id))
            c3_fix.commit()
            c3_fix.close()
        return

    if state == "ASK_BANK_NAME":
        c3.execute(f"UPDATE {tbl} SET bank_name = ?, state = 'ASK_ACCOUNT_NO' WHERE seller_id = ?", (text, user_id))
        conn3.commit()
        conn3.close()
        bot.send_message(user_id, f"Got it — *{text}* ✅\n\nWhat's your account number? 👇", parse_mode="Markdown")
        return

    if state == "ASK_ACCOUNT_NO":
        if not text.isdigit() or len(text) < 10:
            conn3.close()
            bot.send_message(user_id, "⚠️ Please enter a valid 10-digit account number.")
            return
        c3.execute(f"UPDATE {tbl} SET account_no = ?, state = 'ASK_ACCOUNT_NAME' WHERE seller_id = ?", (text, user_id))
        conn3.commit()
        conn3.close()
        bot.send_message(user_id, "Perfect! 👌\n\nWhat's the account name on that account?")
        return

    if state == "ASK_ACCOUNT_NAME":
        c3.execute(f"UPDATE {tbl} SET account_name = ?, state = 'ASK_DELIVERY_HRS' WHERE seller_id = ?", (text, user_id))
        conn3.commit()
        conn3.close()
        kb = ReplyKeyboardMarkup(resize_keyboard=True, one_time_keyboard=True)
        kb.row(KeyboardButton("6 hours"), KeyboardButton("12 hours"))
        kb.row(KeyboardButton("24 hours"), KeyboardButton("48 hours"))
        bot.send_message(user_id,
            "How long does it typically take for orders to reach the buyer?\n_(Sets the escrow release timer)_",
            reply_markup=kb)
        return

    if state == "ASK_DELIVERY_HRS":
        hrs_map = {"6 hours": 6, "12 hours": 12, "24 hours": 24, "48 hours": 48}
        hrs = hrs_map.get(text)
        if not hrs:
            conn3.close()
            bot.send_message(user_id, "Please pick one of the options 👆")
            return
        c3.execute(f"UPDATE {tbl} SET delivery_hrs = ?, state = 'ASK_BIO' WHERE seller_id = ?", (hrs, user_id))
        conn3.commit()
        conn3.close()
        bot.send_message(user_id,
            "Almost done! 🎉\n\nWrite a short bio for your shop\n_(What you sell, where you're based, anything buyers should know)_\n\nOr type *SKIP* to leave it blank.",
            parse_mode="Markdown")
        return

    if state == "ASK_BIO":
        bio = None if lower == "skip" else text
        c3.execute(f"SELECT shop_name, bank_name, account_no, account_name, delivery_hrs FROM {tbl} WHERE seller_id = ?", (user_id,))
        s = c3.fetchone()

        if oil:
            c3.execute(f"SELECT company_name FROM {tbl} WHERE seller_id = ?", (user_id,))
            comp = c3.fetchone()
            company_name = comp[0] if comp else ""
            c3.execute("""INSERT OR REPLACE INTO oil_sellers
                         (seller_id, shop_name, company_name, bank_name, account_no, account_name,
                          delivery_hrs, is_approved, tc_agreed, tc_agreed_at, joined_at, bio)
                         VALUES (?, ?, ?, ?, ?, ?, ?, 0, 1, ?, ?, ?)""",
                      (user_id, s[0], company_name, s[1], s[2], s[3], s[4],
                       utcnow(), utcnow(), bio))
        else:
            c3.execute("""INSERT OR REPLACE INTO sellers
                         (seller_id, shop_name, bank_name, account_no, account_name,
                          delivery_hrs, is_approved, tc_agreed, tc_agreed_at, joined_at, bio)
                         VALUES (?, ?, ?, ?, ?, ?, 0, 1, ?, ?, ?)""",
                      (user_id, s[0], s[1], s[2], s[3], s[4],
                       utcnow(), utcnow(), bio))

        c3.execute(f"DELETE FROM {tbl} WHERE seller_id = ?", (user_id,))
        conn3.commit()
        conn3.close()

        conn_sub = get_conn()
        c_sub = conn_sub.cursor()
        c_sub.execute("UPDATE seller_sessions SET state = 'AWAITING_SUBSCRIPTION_RECEIPT' WHERE seller_id = ?", (user_id,))
        conn_sub.commit()
        conn_sub.close()
        bot.send_message(user_id,
            "One last step!\n\n"
            "Pay your monthly subscription to activate your shop:\n\n"
            f"Amount: N12,500\n"
            f"Bank: {ESCROW_BANK}\n"
            f"Account: {ESCROW_ACCOUNT}\n"
            f"Name: {ESCROW_NAME}\n\n"
            "Send your payment receipt here."
        )
        return

        bot.send_message(user_id,
            f"🎊 *Application Submitted!*\n\nShop: *{s[0]}*\nBank: {s[1]} — `{s[2]}`\nDelivery: {s[4]}hrs\n\nWaiting for OnTabs approval! 🚀",
            reply_markup=ReplyKeyboardRemove()
        )
        industry_label = "Oil" if oil else "Fabric"
        safe_bio = (bio or "None").replace("*","").replace("`","").replace("_","").replace("[","")
        safe_name = (message.from_user.first_name or "").replace("*","").replace("`","").replace("_","")
        safe_shop = (s[0] or "").replace("*","").replace("`","").replace("_","")
        bot.send_message(ADMIN_ID,
            f"New Seller {industry_label}\n\n"
            f"Name: {safe_name}\nID: `{user_id}`\n"
            f"Shop: *{safe_shop}*\nBank: {s[1]} — `{s[2]}`\nAccount: {s[3]}\nDelivery: {s[4]}hrs\n"
            f"Bio: {safe_bio}\n\n"
            f"/approve {user_id}{'_oil' if oil else ''}",
        )

# ═══════════════════════════════════════════════════════
#  ADMIN COMMANDS
# ═══════════════════════════════════════════════════════
@bot.message_handler(commands=['approve'])
def cmd_approve(message):
    if message.chat.id != ADMIN_ID: return
    try:
        parts = message.text.split()
        raw   = parts[1]
        oil   = raw.endswith("_oil")
        seller_id = int(raw.replace("_oil", ""))
        db  = OIL_DB if oil else MAIN_DB
        tbl = "oil_sellers" if oil else "sellers"
        conn = get_conn(db)
        c = conn.cursor()
        c.execute(f"UPDATE {tbl} SET is_approved = 1 WHERE seller_id = ?", (seller_id,))
        conn.commit()
        c.execute(f"SELECT shop_name FROM {tbl} WHERE seller_id = ?", (seller_id,))
        shop = c.fetchone()
        conn.close()
        log_event("SELLER_APPROVED", f"Seller {seller_id} shop={shop[0]}")
        bot.reply_to(message, f"✅ *{shop[0]}* is now LIVE!", parse_mode="Markdown")
        bot.send_message(seller_id,
            f"🎉 *Your shop is LIVE on OnTabs!*\n\nStart with /addproduct\nSee your dashboard with /start 🚀",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message, f"Usage: /approve [id] or /approve [id]_oil\nError: {e}")

@bot.message_handler(commands=['approvebuyer'])
def cmd_approvebuyer(message):
    if message.chat.id != ADMIN_ID: return
    try:
        buyer_id = int(message.text.split()[1])
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE buyer_profiles SET is_approved = 1, approved_at = ?, approved_by = ? WHERE user_id = ?",
                  (utcnow(), ADMIN_ID, buyer_id))
        if conn.total_changes == 0:
            conn.close()
            bot.reply_to(message, f"❌ Buyer `{buyer_id}` not found.", parse_mode="Markdown")
            return
        conn.commit()
        c.execute("SELECT full_name FROM buyer_profiles WHERE user_id = ?", (buyer_id,))
        row = c.fetchone()
        conn.close()
        log_event("BUYER_APPROVED", f"Buyer {buyer_id} approved by admin {ADMIN_ID}")
        bot.reply_to(message, f"✅ Buyer `{buyer_id}` (*{row[0] or 'Unknown'}*) approved!", parse_mode="Markdown")
        bot.send_message(buyer_id,
            "🎉 *Your OnTabs account has been approved!*\n\n"
            "Welcome to the marketplace! Type /start to begin shopping 🛍️",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message, f"Usage: /approvebuyer [user_id]\nError: {e}")

@bot.message_handler(commands=['pendingbuyers'])
def cmd_pendingbuyers(message):
    if message.chat.id != ADMIN_ID: return
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT user_id, full_name, joined_at FROM buyer_profiles WHERE is_approved = 0 AND is_blacklist = 0 ORDER BY joined_at DESC")
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.reply_to(message, "✅ No pending buyers right now!")
        return
    lines = ["⏳ *Buyers Awaiting Approval:*\n"]
    for r in rows:
        lines.append(f"`{r[0]}` — {r[1] or 'No name'} | Joined: {r[2][:10] if r[2] else 'N/A'}\n/approvebuyer {r[0]}")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['release'])
def cmd_release(message):
    if message.chat.id != ADMIN_ID: return
    try:
        ref = message.text.split()[1].upper()
        _release_order(ref, message)
    except Exception as e:
        bot.reply_to(message, f"Usage: /release [OT-XXXXXXXXX]\nError: {e}")

def _release_order(ref, message=None):
    for db, tbl_o, tbl_s in [(MAIN_DB, "orders", "sellers"), (OIL_DB, "oil_orders", "oil_sellers")]:
        conn = get_conn(db)
        c = conn.cursor()
        c.execute(f"""SELECT o.seller_id, o.seller_receives, o.buyer_id, o.item_desc,
                             s.shop_name, s.bank_name, s.account_no, s.account_name
                      FROM {tbl_o} o JOIN {tbl_s} s ON o.seller_id = s.seller_id
                      WHERE o.reference = ?""", (ref,))
        order = c.fetchone()
        if order:
            c.execute(f"UPDATE {tbl_o} SET frozen = 0, status = 'RELEASED', released_at = ? WHERE reference = ?",
                      (utcnow(), ref))
            c.execute(f"UPDATE {tbl_s} SET total_paid_out = total_paid_out + ? WHERE seller_id = ?",
                      (order[1], order[0]))
            conn.commit()
            conn.close()
            msg = f"✅ *Funds Released!*\nRef: `{ref}`\nAmount: ₦{order[1]:,.0f}\nTo: {order[5]} — `{order[6]}` ({order[7]})"
            if message:
                bot.reply_to(message, msg, parse_mode="Markdown")
            else:
                bot.send_message(ADMIN_ID, f"⏰ Auto-Released `{ref}` — ₦{order[1]:,.0f}", parse_mode="Markdown")
            bot.send_message(order[0], f"💚 *Payment Released!*\nRef: `{ref}`\nAmount: ₦{order[1]:,.0f}\n\nCheck your account 🎉", parse_mode="Markdown")
            bot.send_message(order[2], f"✅ Your order `{ref}` is complete. Thanks for shopping on OnTabs! 🛍️")
            return
        conn.close()

@bot.message_handler(commands=['freeze'])
def cmd_freeze(message):
    if message.chat.id != ADMIN_ID: return
    try:
        ref = message.text.split()[1].upper()
        for db, tbl in [(MAIN_DB, "orders"), (OIL_DB, "oil_orders")]:
            conn = get_conn(db)
            c = conn.cursor()
            c.execute(f"UPDATE {tbl} SET frozen = 1, status = 'FROZEN' WHERE reference = ?", (ref,))
            if conn.total_changes > 0:
                conn.commit()
                conn.close()
                bot.reply_to(message, f"🔴 Order `{ref}` FROZEN.", parse_mode="Markdown")
                return
            conn.close()
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['orders'])
def cmd_orders(message):
    if message.chat.id != ADMIN_ID: return
    lines = ["📋 *Recent Orders:*\n"]
    for db, label in [(MAIN_DB, "Fabric"), (OIL_DB, "Oil")]:
        tbl = "orders" if db == MAIN_DB else "oil_orders"
        conn = get_conn(db)
        c = conn.cursor()
        c.execute(f"SELECT reference, buyer_name, item_desc, gross_amount, status, frozen FROM {tbl} ORDER BY created_at DESC LIMIT 10")
        rows = c.fetchall()
        conn.close()
        if rows:
            lines.append(f"*— {label} —*")
            for r in rows:
                tag = " 🔴" if r[5] else ""
                lines.append(f"`{r[0]}`{tag}\n{r[1]} | {r[2]} | ₦{r[3]:,.0f} | {r[4]}\n")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['sellers'])
def cmd_sellers(message):
    if message.chat.id != ADMIN_ID: return
    lines = ["🏪 *All Sellers:*\n"]
    for db, label in [(MAIN_DB, "Fabric"), (OIL_DB, "Oil")]:
        tbl = "sellers" if db == MAIN_DB else "oil_sellers"
        conn = get_conn(db)
        c = conn.cursor()
        c.execute(f"SELECT seller_id, shop_name, is_approved FROM {tbl} ORDER BY joined_at DESC")
        rows = c.fetchall()
        conn.close()
        if rows:
            lines.append(f"*— {label} —*")
            for r in rows:
                lines.append(f"`{r[0]}` — *{r[1]}* | {'✅ Live' if r[2] else '⏳ Pending'}")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['selleraccounts'])
def cmd_selleraccounts(message):
    if message.chat.id != ADMIN_ID: return
    lines = ["🏦 *Seller Bank Accounts:*\n"]
    for db, label in [(MAIN_DB, "Fabric"), (OIL_DB, "Oil")]:
        tbl = "sellers" if db == MAIN_DB else "oil_sellers"
        conn = get_conn(db)
        c = conn.cursor()
        c.execute(f"SELECT seller_id, shop_name, bank_name, account_no, account_name, total_earned, total_paid_out FROM {tbl} WHERE is_approved = 1")
        rows = c.fetchall()
        conn.close()
        if rows:
            lines.append(f"*— {label} Sellers —*")
            for r in rows:
                owed = (r[5] or 0) - (r[6] or 0)
                lines.append(
                    f"*{r[1]}* (`{r[0]}`)\n"
                    f"🏦 {r[2]} — `{r[3]}` ({r[4]})\n"
                    f"Earned: ₦{r[5] or 0:,.0f} | Paid: ₦{r[6] or 0:,.0f} | Owed: ₦{owed:,.0f}\n"
                )
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['unpaid'])
def cmd_unpaid(message):
    if message.chat.id != ADMIN_ID: return
    lines = ["⏳ *Sellers With Pending Payouts:*\n"]
    for db, label in [(MAIN_DB, "Fabric"), (OIL_DB, "Oil")]:
        tbl_o = "orders" if db == MAIN_DB else "oil_orders"
        tbl_s = "sellers" if db == MAIN_DB else "oil_sellers"
        conn = get_conn(db)
        c = conn.cursor()
        c.execute(f"""SELECT s.seller_id, s.shop_name, s.bank_name, s.account_no, s.account_name,
                             SUM(o.seller_receives) as owed
                      FROM {tbl_o} o JOIN {tbl_s} s ON o.seller_id = s.seller_id
                      WHERE o.status = 'RELEASED' AND o.released_at IS NULL
                      GROUP BY s.seller_id""")
        rows = c.fetchall()
        conn.close()
        if rows:
            lines.append(f"*— {label} —*")
            for r in rows:
                lines.append(f"*{r[1]}* | {r[2]} `{r[3]}` ({r[4]}) | ₦{r[5]:,.0f}")
    if len(lines) == 1:
        lines.append("All sellers are up to date ✅")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['buyertabs'])
def cmd_buyertabs(message):
    if message.chat.id != ADMIN_ID: return
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT o.buyer_id, o.buyer_name, o.buyer_phone, COUNT(*) as cnt, SUM(o.gross_amount) as total
                 FROM orders o
                 WHERE o.status = 'AWAITING_PAYMENT'
                 GROUP BY o.buyer_id""")
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.reply_to(message, "No open buyer tabs right now ✅")
        return
    lines = ["📑 *Open Buyer Tabs:*\n"]
    for r in rows:
        lines.append(f"`{r[0]}` — {r[1]} | 📞 {r[2]}\n{r[3]} pending order(s) | ₦{r[4]:,.0f} total\n/blacklist {r[0]}")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['blacklist'])
def cmd_blacklist(message):
    if message.chat.id != ADMIN_ID: return
    try:
        uid = int(message.text.split()[1])
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE buyer_profiles SET is_blacklist = 1 WHERE user_id = ?", (uid,))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"🚫 User `{uid}` has been blacklisted.", parse_mode="Markdown")
        bot.send_message(uid, "🚫 Your OnTabs account has been restricted due to a policy violation.")
    except Exception as e:
        bot.reply_to(message, f"Usage: /blacklist [user_id]\nError: {e}")

@bot.message_handler(commands=['suspicious'])
def cmd_suspicious(message):
    if message.chat.id != ADMIN_ID: return
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT reference, buyer_name, buyer_phone, gross_amount, paid_at, buy_attempt
                 FROM orders WHERE status = 'PAID' AND buy_attempt > 1
                 ORDER BY paid_at DESC LIMIT 20""")
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.reply_to(message, "No suspicious orders flagged ✅")
        return
    lines = ["⚠️ *Suspicious Orders:*\n"]
    for r in rows:
        lines.append(f"`{r[0]}` — {r[1]} | {r[2]}\n₦{r[3]:,.0f} | Attempts: {r[5]} | {r[4][:16] if r[4] else 'N/A'}\n")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['debug'])
def cmd_debug(message):
    if message.chat.id != ADMIN_ID: return
    try:
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM sellers WHERE is_approved = 1")
        sellers = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM orders")
        orders = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM buyer_profiles")
        buyers = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM buyer_profiles WHERE is_approved = 1")
        approved_buyers = c.fetchone()[0]
        conn.close()
        conn2 = get_conn(OIL_DB)
        c2 = conn2.cursor()
        c2.execute("SELECT COUNT(*) FROM oil_sellers WHERE is_approved = 1")
        oil_sellers = c2.fetchone()[0]
        c2.execute("SELECT COUNT(*) FROM oil_orders")
        oil_orders = c2.fetchone()[0]
        conn2.close()
        bot.reply_to(message,
            f"🔧 *OnTabs Debug Status*\n\n"
            f"Fabric Sellers: {sellers}\nFabric Orders: {orders}\n"
            f"Oil Sellers: {oil_sellers}\nOil Orders: {oil_orders}\n"
            f"Buyers: {buyers} (Approved: {approved_buyers})\n\n"
            f"DBs: `{MAIN_DB}` ✅ | `{OIL_DB}` ✅\n"
            f"Scheduler: Running ✅",
            parse_mode="Markdown"
        )
    except Exception as e:
        bot.reply_to(message, f"❌ Debug error: {e}")

# ═══════════════════════════════════════════════════════
#  SELLER PRODUCT COMMANDS
# ═══════════════════════════════════════════════════════
@bot.message_handler(commands=['addproduct', 'addstock'])
def cmd_addproduct(message):
    oil = is_seller(message.chat.id, oil=True)
    if not is_seller(message.chat.id) and not oil:
        bot.reply_to(message, "🚫 Approved sellers only.")
        return
    try:
        _, parts = message.text.split(maxsplit=1)
        if oil:
            # Format: /addproduct Name, Price, Stock, Unit
            name, price, stock, unit = [p.strip() for p in parts.split(",")]
            conn = get_conn(OIL_DB)
            c = conn.cursor()
            c.execute("INSERT INTO oil_products (seller_id, name, price, stock, unit) VALUES (?, ?, ?, ?, ?)",
                      (message.chat.id, name, float(price), int(stock), unit))
            conn.commit()
            conn.close()
            bot.reply_to(message,
                f"✅ *{name}* added!\nPrice: ₦{float(price):,} per {unit} | Stock: {stock} {unit}",
                parse_mode="Markdown"
            )
        else:
            # Format: /addproduct Category, Name/Color, Price, Stock, Unit, Gender
            cat, color, price, stock, unit, gender = [p.strip() for p in parts.split(",")]
            conn = get_conn()
            c = conn.cursor()
            c.execute("INSERT INTO products (seller_id, category, color, price, stock, unit, gender) VALUES (?, ?, ?, ?, ?, ?, ?)",
                      (message.chat.id, cat.capitalize(), color.capitalize(), float(price), int(stock), unit, gender.capitalize()))
            conn.commit()
            conn.close()
            bot.reply_to(message,
                f"✅ *{color} {cat}* added!\nPrice: ₦{float(price):,} per {unit} | Stock: {stock} {unit} | {gender}",
                parse_mode="Markdown"
            )
    except Exception as e:
        if is_seller(message.chat.id, oil=True):
            bot.reply_to(message, f"⚠️ Format: /addproduct Name, Price, Stock, Unit\nExample: /addproduct Palm Oil, 2500, 50, Liters\nError: {e}")
        else:
            bot.reply_to(message, f"⚠️ Format: /addproduct Category, Color, Price, Stock, Unit, Gender\nExample: /addproduct Lace, Royal Blue, 3500, 20, yards, Female\nError: {e}")

# Alias
@bot.message_handler(commands=['updatestock', 'editstock'])
def cmd_updatestock(message):
    cmd_addproduct(message)

@bot.message_handler(commands=['mystock', 'viewstock', 'catalog'])
def cmd_mystock(message):
    user_id = message.chat.id
    oil = is_seller(user_id, oil=True)
    if not is_seller(user_id) and not oil:
        bot.reply_to(message, "🚫 Approved sellers only.")
        return

    if oil:
        conn = get_conn(OIL_DB)
        c = conn.cursor()
        c.execute("SELECT id, name, price, stock, unit FROM oil_products WHERE seller_id = ?", (user_id,))
        rows = c.fetchall()
        conn.close()
        if not rows:
            bot.reply_to(message, "📭 No products yet. Use /addproduct")
            return
        lines = ["📦 *Your Oil Catalog:*\n"]
        for r in rows:
            stock_label = f"{r[3]} {r[4]}" if r[3] >= 0 else "In Stock"
            lines.append(f"[{r[0]}] *{r[1]}* — ₦{r[2]:,}/{r[4]} | {stock_label}")
    else:
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT id, category, color, price, stock, unit, gender FROM products WHERE seller_id = ?", (user_id,))
        rows = c.fetchall()
        conn.close()
        if not rows:
            bot.reply_to(message, "📭 No products yet. Use /addproduct")
            return
        lines = ["📦 *Your Catalog:*\n"]
        for r in rows:
            stock_label = f"{r[4]} {r[5]}" if r[4] >= 0 else "In Stock"
            lines.append(f"[{r[0]}] *{r[2]} {r[1]}* — ₦{r[3]:,}/{r[5]} | {stock_label} | {r[6]}")

    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

@bot.message_handler(commands=['myorders', 'vieworders', 'orders_mine'])
def cmd_myorders(message):
    user_id = message.chat.id
    oil = is_seller(user_id, oil=True)
    if not is_seller(user_id) and not oil:
        return

    db  = OIL_DB if oil else MAIN_DB
    tbl = "oil_orders" if oil else "orders"

    conn = get_conn(db)
    c = conn.cursor()
    c.execute(f"""SELECT reference, buyer_name, buyer_phone, buyer_address,
                         item_desc, quantity, unit, gross_amount, seller_receives, status, frozen
                  FROM {tbl} WHERE seller_id = ? ORDER BY created_at DESC LIMIT 15""", (user_id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.reply_to(message, "No orders yet. Keep pushing! 💪")
        return
    lines = ["📋 *Your Orders:*\n"]
    for r in rows:
        tag = " 🔴" if r[10] else ""
        lines.append(
            f"`{r[0]}`{tag}\n"
            f"👤 {r[1]} | 📞 {r[2]}\n"
            f"📍 {r[3]}\n"
            f"📦 {r[4]} x{r[5]} {r[6]}\n"
            f"₦{r[7]:,.0f} → You get ₦{r[8]:,.0f} | {r[9]}\n"
        )
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")

# ═══════════════════════════════════════════════════════
#  ANNOUNCEMENT SYSTEM
# ═══════════════════════════════════════════════════════
@bot.message_handler(commands=['setannounce'])
def cmd_setannounce(message):
    if message.chat.id != ADMIN_ID: return
    try:
        parts   = message.text.split()
        count   = int(parts[1])
        grp_id  = int(parts[2])
        if not (5 <= count <= 30):
            bot.reply_to(message, "Count must be between 5 and 30.")
            return
        conn = get_conn()
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO announcement_config (id, times_day, group_id) VALUES (1, ?, ?)",
                  (count, grp_id))
        conn.commit()
        conn.close()
        bot.reply_to(message, f"✅ Bot will post *{count}x/day* to group `{grp_id}`.", parse_mode="Markdown")
        reschedule_announcements()
    except Exception as e:
        bot.reply_to(message, f"Usage: /setannounce [5-30] [group_id]\nError: {e}")

@bot.message_handler(commands=['announce'])
def cmd_announce_now(message):
    if message.chat.id != ADMIN_ID: return
    do_announcement()
    bot.reply_to(message, "📢 Announcement sent!")

def do_announcement():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT group_id FROM announcement_config WHERE id = 1")
    cfg = c.fetchone()
    if not cfg or not cfg[0]:
        conn.close()
        return
    group_id = cfg[0]

    # Fabric sellers
    c.execute("""SELECT s.shop_name, GROUP_CONCAT(p.category || ' (' || p.color || ') ₦' || p.price || '/' || p.unit) as items
                 FROM sellers s JOIN products p ON s.seller_id = p.seller_id
                 WHERE s.is_approved = 1 GROUP BY s.seller_id""")
    fabric_rows = c.fetchall()
    conn.close()

    # Oil sellers
    conn2 = get_conn(OIL_DB)
    c2 = conn2.cursor()
    c2.execute("""SELECT s.shop_name, GROUP_CONCAT(p.name || ' ₦' || p.price || '/' || p.unit) as items
                  FROM oil_sellers s JOIN oil_products p ON s.seller_id = p.seller_id
                  WHERE s.is_approved = 1 GROUP BY s.seller_id""")
    oil_rows = c2.fetchall()
    conn2.close()

    lines = ["🌅 *OnTabs Marketplace — Live Now*\n"]
    if fabric_rows:
        lines.append("🧵 *Fabric & Fashion*")
        for shop, items in fabric_rows:
            lines.append(f"🔹 *{shop}*\n   {items}")
    if oil_rows:
        lines.append("\n🫙 *Oil*")
        for shop, items in oil_rows:
            lines.append(f"🔹 *{shop}*\n   {items}")
    lines.append("\n_DM the bot to order securely via OnTabs escrow_ 🛡️")

    try:
        bot.send_message(group_id, "\n".join(lines), parse_mode="Markdown")
    except Exception as e:
        print(f"Announcement failed: {e}")

scheduler = BackgroundScheduler()
announce_jobs = []

def reschedule_announcements():
    global announce_jobs
    for job in announce_jobs:
        try:
            job.remove()
        except:
            pass
    announce_jobs = []
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT times_day FROM announcement_config WHERE id = 1")
    cfg = c.fetchone()
    conn.close()
    if not cfg:
        return
    count = cfg[0]
    # Spread randomly across waking hours 7am–10pm
    minutes_in_window = (22 - 7) * 60
    chosen_minutes = sorted(random.sample(range(minutes_in_window), min(count, minutes_in_window)))
    for m in chosen_minutes:
        hr  = 7 + m // 60
        mn  = m % 60
        job = scheduler.add_job(do_announcement, 'cron', hour=hr, minute=mn)
        announce_jobs.append(job)

# ═══════════════════════════════════════════════════════
#  SEARCH — BUYERS
# ═══════════════════════════════════════════════════════
def search_marketplace(query):
    """Search by shop name, category/product name, industry."""
    results = []
    q = f"%{query.lower()}%"

    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT DISTINCT s.seller_id, s.shop_name, s.bio,
                        GROUP_CONCAT(DISTINCT p.category) as cats
                 FROM sellers s JOIN products p ON s.seller_id = p.seller_id
                 WHERE s.is_approved = 1 AND (
                     LOWER(s.shop_name) LIKE ? OR
                     LOWER(p.category)  LIKE ? OR
                     LOWER(p.color)     LIKE ? OR
                     LOWER(s.bio)       LIKE ?
                 )
                 GROUP BY s.seller_id""", (q, q, q, q))
    for row in c.fetchall():
        results.append(("fabric", row[0], row[1], row[2], row[3]))
    conn.close()

    conn2 = get_conn(OIL_DB)
    c2 = conn2.cursor()
    c2.execute("""SELECT DISTINCT s.seller_id, s.shop_name, s.bio,
                         GROUP_CONCAT(DISTINCT p.name) as products
                  FROM oil_sellers s JOIN oil_products p ON s.seller_id = p.seller_id
                  WHERE s.is_approved = 1 AND (
                      LOWER(s.shop_name)    LIKE ? OR
                      LOWER(s.company_name) LIKE ? OR
                      LOWER(p.name)         LIKE ? OR
                      LOWER(s.bio)          LIKE ?
                  )
                  GROUP BY s.seller_id""", (q, q, q, q))
    for row in c2.fetchall():
        results.append(("oil", row[0], row[1], row[2], row[3]))
    conn2.close()

    return results

# ═══════════════════════════════════════════════════════
#  RECEIPT HANDLER
# ═══════════════════════════════════════════════════════
def handle_receipt(message):
    user_id = message.chat.id
    session = get_session(user_id)

    if not session or session[0] != "AWAITING_RECEIPT":
        bot.reply_to(message, "Thanks! But I'm not expecting a receipt from you right now. Type /start for help 😊")
        return

    industry = session[6] or "Fabric"
    oil = (industry == "Oil")
    db    = OIL_DB if oil else MAIN_DB
    tbl_o = "oil_orders" if oil else "orders"
    tbl_s = "oil_sellers" if oil else "sellers"

    conn = get_conn(db)
    c = conn.cursor()
    c.execute(f"""SELECT reference, seller_id, item_desc, quantity, unit, gross_amount, seller_receives, product_id,
                         buyer_address, buyer_phone, buyer_landmark
                  FROM {tbl_o} WHERE buyer_id = ? AND status = 'AWAITING_PAYMENT'
                  ORDER BY created_at DESC LIMIT 1""", (user_id,))
    order = c.fetchone()

    if not order:
        conn.close()
        bot.reply_to(message, "No pending order found. Type /start to begin again.")
        return

    ref, seller_id, item_desc, qty, unit, gross, seller_gets, p_id, addr, phone, landmark = order

    # Increment buy_attempt for fraud detection
    if not oil:
        c.execute("UPDATE orders SET buy_attempt = buy_attempt + 1 WHERE reference = ?", (ref,))

    c.execute(f"SELECT delivery_hrs, shop_name FROM {tbl_s} WHERE seller_id = ?", (seller_id,))
    seller_info = c.fetchone()
    delivery_hrs = seller_info[0] if seller_info else 24
    shop_name    = seller_info[1] if seller_info else "the seller"
    release_at   = datetime.now() + timedelta(hours=delivery_hrs)

    c.execute(f"UPDATE {tbl_o} SET status = 'PAID', paid_at = ?, release_at = ?, receipt_msg_id = ? WHERE reference = ?",
              (utcnow(), release_at.isoformat(), message.message_id, ref))

    if not oil and p_id:
        c.execute("UPDATE products SET stock = stock - ? WHERE id = ? AND stock >= 0", (qty, p_id))

    c.execute(f"UPDATE {tbl_s} SET total_earned = total_earned + ? WHERE seller_id = ?", (seller_gets, seller_id))

    conn.commit()
    conn.close()

    # Update buyer profile
    conn3 = get_conn()
    c3 = conn3.cursor()
    c3.execute("""UPDATE buyer_profiles SET total_orders = total_orders + 1, total_spent = total_spent + ?
                  WHERE user_id = ?""", (gross, user_id))
    conn3.commit()
    conn3.close()

    set_session_state(user_id, "BROWSING")

    bot.reply_to(message,
        f"✅ *Receipt received!*\n\nRef: `{ref}`\n🔒 Funds held in escrow.\n"
        f"⏰ Auto-releases to *{shop_name}* in *{delivery_hrs} hours*.\n\nYour item is on its way! 🎉",
        parse_mode="Markdown"
    )

    # Forward receipt to SELLER directly
    bot.forward_message(seller_id, message.chat.id, message.message_id)
    bot.send_message(seller_id,
        f"💛 *Payment Confirmed!*\n"
        f"Ref: `{ref}`\n"
        f"Item: {item_desc} x{qty} {unit}\n"
        f"You earn: ₦{seller_gets:,.0f}\n\n"
        f"📍 *Dispatch To:*\n"
        f"Address: {addr}\n"
        f"Landmark: {landmark or 'N/A'}\n"
        f"Phone: {phone}\n\n"
        f"Dispatch now! 🚚",
        parse_mode="Markdown"
    )

    # Forward receipt + details to ADMIN
    bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
    bot.send_message(ADMIN_ID,
        f"📸 *Receipt — {ref}*\n"
        f"Buyer: {(message.from_user.first_name or '').replace('*','').replace('`','').replace('_','')} (`{user_id}`)\n"
        f"Phone: {phone}\nAddress: {addr}\nLandmark: {landmark or 'N/A'}\n"
        f"Item: {item_desc} x{qty} {unit} | ₦{gross:,.0f}\n"
        f"Auto-release: {release_at.strftime('%d %b, %I:%M %p')}\n\n"
        f"/release {ref} | /freeze {ref}",
        parse_mode="Markdown"
    )

# ═══════════════════════════════════════════════════════
#  AUTO RELEASE
# ═══════════════════════════════════════════════════════
def auto_release_check():
    now = utcnow()
    for db, tbl_o, tbl_s in [(MAIN_DB, "orders", "sellers"), (OIL_DB, "oil_orders", "oil_sellers")]:
        conn = get_conn(db)
        c = conn.cursor()
        # FIX: Only release PAID orders where frozen = 0
        c.execute(f"""SELECT o.reference, o.buyer_id, o.seller_id, o.seller_receives
                      FROM {tbl_o} o
                      WHERE o.status = 'PAID' AND o.frozen = 0 AND o.release_at <= ?""", (now,))
        for ref, buyer_id, seller_id, seller_gets in c.fetchall():
            _release_order(ref)
        conn.close()

# ═══════════════════════════════════════════════════════
#  MAIN HANDLER
# ═══════════════════════════════════════════════════════
@bot.message_handler(content_types=['text', 'photo'])
def main_handler(message):
    user_id = message.chat.id
    text    = message.text.strip() if message.text else ""
    lower   = text.lower()

    if is_blacklisted(user_id):
        bot.reply_to(message, "🚫 Your account is restricted.")
        return

    # Seller registration triggers
    if lower in ["🏪 i want to sell", "i want to sell"]:
        bot.send_message(user_id,
            "Great! Which industry are you selling in? 👇",
            reply_markup=industry_keyboard()
        )
        return

    if lower == "🫙 oil":
        start_oil_seller_reg(message)
        return
    elif lower in ["🛠️ services", "services"]:
        start_service_buyer_flow(message)
        return
    elif lower in ["🛠️ i offer services", "i offer services"]:
        start_service_seller_reg(message)
        return
        return

    if lower == "🧵 fabric & fashion":
        start_seller_reg(message, industry="Fabric")
        return

    # Mid-registration
    if is_pending_seller(user_id, oil=True):
        handle_seller_reg(message, oil=True)
        return

    if is_pending_seller(user_id):
        conn_sub = get_conn()
        c_sub = conn_sub.cursor()
        c_sub.execute("SELECT state FROM seller_sessions WHERE seller_id = ?", (user_id,))
        fab_sess = c_sub.fetchone()
        conn_sub.close()
        if fab_sess and fab_sess[0] == "AWAITING_SUBSCRIPTION_RECEIPT" and message.content_type == "photo":
            conn_sub2 = get_conn()
            c_sub2 = conn_sub2.cursor()
            c_sub2.execute("SELECT shop_name, bank_name, account_no, delivery_hrs FROM seller_sessions WHERE seller_id = ?", (user_id,))
            info = c_sub2.fetchone()
            conn_sub2.close()
            bot.reply_to(message, "Receipt received! Awaiting admin approval.")
            bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
            if info:
                bot.send_message(ADMIN_ID,
                    f"Subscription Receipt\n\n"
                    f"ID: {user_id}\n"
                    f"Shop: {info[0]}\n"
                    f"Bank: {info[1]} - {info[2]}\n"
                    f"Delivery: {info[3]}hrs\n\n"
                    f"/approve {user_id}"
                )
            return
        handle_seller_reg(message, oil=False)
        return

    # Service seller check
    conn_srv = get_conn()
    c_srv = conn_srv.cursor()
    c_srv.execute("SELECT seller_id FROM service_seller_sessions WHERE seller_id = ?", (user_id,))
    is_srv_pending = c_srv.fetchone()
    conn_srv.close()
    if is_srv_pending:
        # Check if awaiting subscription receipt
        conn_sub = get_conn()
        c_sub = conn_sub.cursor()
        c_sub.execute("SELECT state FROM service_seller_sessions WHERE seller_id = ?", (user_id,))
        srv_sess = c_sub.fetchone()
        conn_sub.close()
        if srv_sess and srv_sess[0] == "AWAITING_SUBSCRIPTION_RECEIPT" and message.content_type == "photo":
            conn_sub2 = get_conn()
            c_sub2 = conn_sub2.cursor()
            c_sub2.execute("SELECT business_name, skill_category, bank_name, account_no FROM service_seller_sessions WHERE seller_id = ?", (user_id,))
            info = c_sub2.fetchone()
            conn_sub2.close()
            bot.reply_to(message, "Receipt received! Awaiting admin approval. You will be notified shortly.")
            bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)
            if info:
                bot.send_message(ADMIN_ID,
                    f"Subscription Receipt\n\n"
                    f"ID: {user_id}\n"
                    f"Business: {info[0]}\n"
                    f"Skill: {info[1]}\n"
                    f"Bank: {info[2]} — {info[3]}\n\n"
                    f"/approve {user_id}"
                )
            return
        handle_service_seller_reg(message)
        return

    # Smart seller/buyer routing — check active buyer session first
    session = get_session(user_id)
    active_buyer_states = {
        "TC_PENDING", "WAITING_FOR_GENDER", "WAITING_FOR_COLOR",
        "WAITING_FOR_OIL_PRODUCT", "WAITING_FOR_QUANTITY", "CONFIRMING",
        "WAITING_FOR_ADDRESS", "WAITING_FOR_LANDMARK", "WAITING_FOR_PHONE",
        "AWAITING_RECEIPT"
    }
    is_actively_buying = (
        lower in ["🛍️ i want to buy", "i want to buy"] or
        (session and session[0] in active_buyer_states) or
        (lower == "agree" and session and session[0] == "TC_PENDING")
    )
    if (is_seller(user_id) or is_seller(user_id, oil=True)) and not is_actively_buying:
        seller_dashboard(message)
        return

    # Receipt photo
    if message.content_type == 'photo':
        handle_receipt(message)
        return

    # Buyer flow
    handle_buyer(message)

# ═══════════════════════════════════════════════════════
#  BUYER FLOW
# ═══════════════════════════════════════════════════════
def handle_buyer(message):
    user_id = message.chat.id
    text    = message.text.strip() if message.text else ""
    lower   = text.lower()

    session = get_session(user_id)

    # ── Approval gate ──
    if not is_buyer_approved(user_id) and not is_seller(user_id) and not is_seller(user_id, oil=True):
        bot.reply_to(message, "⏳ Your account is pending admin approval. Please wait — you'll be notified once approved.")
        return

    # ── T&C gate ──
    if lower == "🛍️ i want to buy" or (not buyer_agreed_tc(user_id) and lower == "agree"):
        if not buyer_agreed_tc(user_id):
            if lower != "agree":
                bot.reply_to(message,
                    f"Before you shop, please read and accept our Buyer Agreement:\n{BUYER_TC}\n\nType *AGREE* to continue.",
                    parse_mode="Markdown",
                    reply_markup=ReplyKeyboardRemove()
                )
                conn = get_conn()
                c = conn.cursor()
                c.execute("INSERT OR REPLACE INTO buyer_sessions (user_id, state) VALUES (?, 'TC_PENDING')", (user_id,))
                conn.commit()
                conn.close()
                return
            else:
                # Agreed
                conn = get_conn()
                c = conn.cursor()
                c.execute("UPDATE buyer_profiles SET tc_agreed = 1, tc_agreed_at = ? WHERE user_id = ?",
                          (utcnow(), user_id))
                c.execute("INSERT INTO tc_log (user_id, role, agreed_at) VALUES (?, 'buyer', ?)",
                          (user_id, utcnow()))
                conn.commit()
                conn.close()
                lower = "🛍️ i want to buy"

        if lower == "🛍️ i want to buy":
            show_industry_selection(message, user_id)
            return

    if session and session[0] == "TC_PENDING" and lower == "agree":
        conn = get_conn()
        c = conn.cursor()
        c.execute("UPDATE buyer_profiles SET tc_agreed = 1, tc_agreed_at = ? WHERE user_id = ?",
                  (utcnow(), user_id))
        c.execute("INSERT INTO tc_log (user_id, role, agreed_at) VALUES (?, 'buyer', ?)",
                  (user_id, utcnow()))
        conn.commit()
        conn.close()
        show_industry_selection(message, user_id)
        return

    # ── Industry selection ──
    if lower == "🫙 oil" and (not session or session[0] in ("BROWSING", "START", None, "TC_PENDING")):
        show_sellers_by_industry(message, user_id, "Oil")
        return

    if lower == "🧵 fabric & fashion" and (not session or session[0] in ("BROWSING", "START", None, "TC_PENDING")):
        show_sellers_by_industry(message, user_id, "Fabric")
        return

    # ── Search ──
    if lower.startswith("search ") or lower.startswith("find "):
        query = text.split(maxsplit=1)[1] if len(text.split()) > 1 else ""
        if query:
            results = search_marketplace(query)
            if not results:
                bot.reply_to(message, f"😔 Nothing found for *{query}*. Try a product name, shop name, or category.", parse_mode="Markdown")
            else:
                lines = [f"🔍 *Results for '{query}':*\n"]
                for ind, sid, shop, bio, items in results:
                    icon = "🫙" if ind == "oil" else "🧵"
                    lines.append(f"{icon} *{shop}*\n_{bio or 'No bio'}_\n📦 {items or 'Various'}\n")
                lines.append("Type the shop name or product to browse 👇")
                bot.reply_to(message, "\n".join(lines), parse_mode="Markdown")
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
        c.execute("UPDATE buyer_sessions SET gender_pref = ?, state = 'WAITING_FOR_COLOR' WHERE user_id = ?", (gender, user_id))
        conn.commit()
        conn.close()
        show_available_colors(message, session[1], gender, session[5])
        return

    # ── Oil product selection ──
    if session and session[0] == "WAITING_FOR_OIL_PRODUCT":
        seller_id = session[5]
        conn = get_conn(OIL_DB)
        c = conn.cursor()
        c.execute("SELECT id, name, price, stock, unit FROM oil_products WHERE seller_id = ? AND LOWER(name) LIKE ?",
                  (seller_id, f"%{lower}%"))
        product = c.fetchone()
        conn.close()
        if product:
            p_id, name, price, stock, unit = product
            stock_label = f"{stock} {unit} available" if stock >= 0 else "In Stock ✅"
            conn2 = get_conn()
            c2 = conn2.cursor()
            c2.execute("UPDATE buyer_sessions SET state = 'WAITING_FOR_QUANTITY', pending_product_id = ? WHERE user_id = ?",
                       (p_id, user_id))
            conn2.commit()
            conn2.close()
            bot.reply_to(message,
                f"🫙 *{name}*\n\n💰 ₦{price:,}/{unit}\n📦 {stock_label}\n\nHow many {unit}? 👇",
                parse_mode="Markdown"
            )
        else:
            bot.reply_to(message, "🤔 Couldn't find that product. Type the product name from the list above.")
        return

    # ── Category detection (Fabric) ──
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT DISTINCT category FROM products")
    all_cats = [row[0].lower() for row in c.fetchall()]
    conn.close()

    male_keys   = ["man", "male", "men", "groom", "atiku", "senator", "agbada"]
    female_keys = ["woman", "female", "lace", "chiffon", "silk", "bride", "asoebi"]
    detected_gender = (
        "Male"   if any(w in lower for w in male_keys) else
        "Female" if any(w in lower for w in female_keys) else None
    )
    matched_cat = next((cat for cat in all_cats if cat in lower), None)

    if matched_cat and (not session or session[0] in ("BROWSING", "START", None)):
        conn2 = get_conn()
        c2 = conn2.cursor()
        c2.execute("""SELECT DISTINCT p.seller_id FROM products p
                      JOIN sellers s ON p.seller_id = s.seller_id
                      WHERE p.category = ? AND s.is_approved = 1 LIMIT 1""", (matched_cat.capitalize(),))
        seller_row = c2.fetchone()
        seller_id  = seller_row[0] if seller_row else None
        c2.execute("INSERT OR REPLACE INTO buyer_sessions (user_id, state, current_category, gender_pref, current_seller_id, industry) VALUES (?, ?, ?, ?, ?, 'Fabric')",
                   (user_id, "WAITING_FOR_GENDER", matched_cat.capitalize(), detected_gender, seller_id))
        conn2.commit()
        conn2.close()

        if detected_gender:
            show_available_colors(message, matched_cat.capitalize(), detected_gender, seller_id)
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
        conn3 = get_conn()
        c3 = conn3.cursor()
        c3.execute("""SELECT id, color, price, stock, unit FROM products
                      WHERE seller_id = ? AND category = ? AND LOWER(color) LIKE ?
                      AND (gender = ? OR gender = 'Unisex') COLLATE NOCASE""",
                   (seller_id, category, f"%{lower}%", gender))
        product = c3.fetchone()
        if product:
            p_id, color, price, stock, unit = product
            stock_label = f"{stock} {unit} available" if stock >= 0 else "In Stock ✅"
            c3.execute("UPDATE buyer_sessions SET state = 'WAITING_FOR_QUANTITY', pending_product_id = ? WHERE user_id = ?",
                       (p_id, user_id))
            conn3.commit()
            conn3.close()
            bot.reply_to(message,
                f"Yes! *{color} {category}* 🎉\n\n💰 ₦{price:,}/{unit}\n📦 {stock_label}\n\nHow many {unit}? 👇",
                parse_mode="Markdown"
            )
        else:
            show_available_colors(message, category, gender, seller_id, not_found=lower)
            conn3.close()
        return

    # ── Quantity ──
    if session and session[0] == "WAITING_FOR_QUANTITY":
        if not text.replace(".", "").isdigit():
            bot.reply_to(message, "Please type a number 😊")
            return

        qty      = int(float(text))
        p_id     = session[3]
        industry = session[6] or "Fabric"
        oil      = (industry == "Oil")
        db       = OIL_DB if oil else MAIN_DB

        conn4 = get_conn(db)
        c4 = conn4.cursor()
        if oil:
            c4.execute("SELECT name, price, stock, unit FROM oil_products WHERE id = ?", (p_id,))
            product = c4.fetchone()
            if not product:
                conn4.close()
                bot.reply_to(message, "⚠️ Something went wrong. Type /start to begin again.")
                return
            name, price, stock, unit = product
            color, category = name, "Oil"
        else:
            c4.execute("SELECT color, price, stock, category, unit FROM products WHERE id = ?", (p_id,))
            product = c4.fetchone()
            if not product:
                conn4.close()
                bot.reply_to(message, "⚠️ Something went wrong. Type /start to begin again.")
                return
            color, price, stock, category, unit = product
            name = f"{color} {category}"

        if stock >= 0 and qty > stock:
            conn4.close()
            bot.reply_to(message, f"😬 Only *{stock} {unit}* left! Enter a smaller amount.", parse_mode="Markdown")
            return

        gross = qty * price
        fee   = round(gross * ONTABS_FEE_PCT, 2)
        total = round(gross + fee, 2)

        conn4.close()

        conn5 = get_conn()
        c5 = conn5.cursor()
        c5.execute("UPDATE buyer_sessions SET state = 'CONFIRMING', quantity = ? WHERE user_id = ?", (qty, user_id))
        conn5.commit()
        conn5.close()

        bot.reply_to(message,
            f"📊 *Order Summary*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"Item: *{name}*\n"
            f"Qty: {qty} {unit}\n"
            f"Price: ₦{price:,}/{unit}\n"
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
        # Prevent duplicate orders
        if has_pending_order(user_id):
            bot.reply_to(message,
                "⚠️ You already have an open order. Please complete or cancel it first.\n"
                "Send your payment receipt or type /start for help.",
                parse_mode="Markdown"
            )
            return
        set_session_state(user_id, "WAITING_FOR_ADDRESS")
        bot.reply_to(message,
            "📍 *Almost there!*\n\nPlease type your *full delivery address*:\n"
            "_(State, LGA, Street, House/Gate number)_\n\n"
            "Example: Lagos, Surulere, 15 Adeleke Street, Gate 3",
            parse_mode="Markdown"
        )
        return

    # ── Address ──
    if session and session[0] == "WAITING_FOR_ADDRESS":
        conn6 = get_conn()
        c6 = conn6.cursor()
        c6.execute("UPDATE buyer_sessions SET state = 'WAITING_FOR_LANDMARK', temp_address = ? WHERE user_id = ?",
                   (text, user_id))
        conn6.commit()
        conn6.close()
        bot.reply_to(message,
            "🏷️ Any *landmark* near your address?\n_(e.g. 'Behind Access Bank', 'Beside Total Filling Station')_\n\nOr type *NONE* to skip.",
            parse_mode="Markdown"
        )
        return

    # ── Landmark ──
    if session and session[0] == "WAITING_FOR_LANDMARK":
        landmark = None if lower == "none" else text
        conn7 = get_conn()
        c7 = conn7.cursor()
        c7.execute("UPDATE buyer_sessions SET state = 'WAITING_FOR_PHONE', current_category = ? WHERE user_id = ?",
                   (landmark or "", user_id))
        conn7.commit()
        conn7.close()
        bot.reply_to(message,
            "📞 *Last step!*\n\nWhat's your phone number so the seller can reach you?\n\nExample: 08012345678",
            parse_mode="Markdown"
        )
        return

    # ── Phone → Create Order ──
    if session and session[0] == "WAITING_FOR_PHONE":
        buyer_phone = text
        addr        = session[7]          # temp_address
        landmark    = session[1]          # current_category temporarily holds landmark
        p_id        = session[3]
        qty         = session[4]
        seller_id   = session[5]
        industry    = session[6] or "Fabric"
        oil         = (industry == "Oil")
        db          = OIL_DB if oil else MAIN_DB
        tbl_o       = "oil_orders" if oil else "orders"
        tbl_s       = "oil_sellers" if oil else "sellers"
        tbl_p       = "oil_products" if oil else "products"

        conn8 = get_conn(db)
        c8 = conn8.cursor()

        if oil:
            c8.execute("SELECT name, price, unit FROM oil_products WHERE id = ?", (p_id,))
            product = c8.fetchone()
            name, price, unit = product
            item_desc = name
        else:
            c8.execute("SELECT color, price, category, unit FROM products WHERE id = ?", (p_id,))
            product = c8.fetchone()
            color, price, category, unit = product
            item_desc = f"{color} {category}"

        gross       = qty * price
        fee         = round(gross * ONTABS_FEE_PCT, 2)
        total       = round(gross + fee, 2)
        seller_gets = gross - fee
        ref         = gen_reference("OT" if not oil else "OIL")

        c8.execute(f"""INSERT INTO {tbl_o}
                     (reference, buyer_id, seller_id, product_id, buyer_name, buyer_phone,
                      buyer_address, buyer_landmark, item_desc, quantity, unit,
                      unit_price, gross_amount, ontabs_fee, seller_receives,
                      status, frozen, created_at)
                     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'AWAITING_PAYMENT', 0, ?)""",
                  (ref, user_id, seller_id, p_id,
                   message.from_user.first_name, buyer_phone,
                   addr, landmark, item_desc, qty, unit,
                   price, gross, fee, seller_gets,
                   utcnow()))

        conn8.commit()
        conn8.close()

        # Update buyer profile phone
        conn9 = get_conn()
        c9 = conn9.cursor()
        c9.execute("UPDATE buyer_profiles SET phone = ?, address = ? WHERE user_id = ?",
                   (buyer_phone, addr, user_id))
        c9.execute("UPDATE buyer_sessions SET state = 'AWAITING_RECEIPT' WHERE user_id = ?", (user_id,))
        conn9.commit()
        conn9.close()

        bot.reply_to(message,
            f"🛡️ *OnTabs Zero-Trust Escrow*\n"
            f"━━━━━━━━━━━━━━━━━━━━\n"
            f"Pay into the OnTabs escrow account:\n\n"
            f"🏦 Bank: *{ESCROW_BANK}*\n"
            f"👤 Name: *{ESCROW_NAME}*\n"
            f"💳 Account: `{ESCROW_ACCOUNT}`\n\n"
            f"💰 *Amount: ₦{total:,.0f}*\n\n"
            f"🔑 *Your Reference:*\n`{ref}`\n\n"
            f"⚠️ _Use this exact reference when transferring._\n\n"
            f"📸 Send your receipt screenshot here once done.",
            parse_mode="Markdown"
        )

        # Notify seller
        conn10 = get_conn(db)
        c10 = conn10.cursor()
        c10.execute(f"SELECT shop_name FROM {tbl_s} WHERE seller_id = ?", (seller_id,))
        shop = c10.fetchone()
        conn10.close()

        bot.send_message(seller_id,
            f"🔔 *New Order!*\nRef: `{ref}`\nItem: *{item_desc}* x{qty} {unit}\n"
            f"Value: ₦{gross:,.0f} | You receive: ₦{seller_gets:,.0f}\n\n"
            f"📍 *Deliver to:*\n{addr}\nLandmark: {landmark or 'N/A'}\n📞 {buyer_phone}\n\n"
            f"⏳ Awaiting buyer payment.",
            parse_mode="Markdown"
        )
        bot.send_message(ADMIN_ID,
            f"🛒 *NEW ORDER*\nRef: `{ref}`\n"
            f"Buyer: {(message.from_user.first_name or '').replace('*','').replace('`','').replace('_','')} (`{user_id}`)\nPhone: {buyer_phone}\n"
            f"Item: {item_desc} x{qty} {unit}\nTotal: ₦{total:,.0f} | Fee: ₦{fee:,.0f} | Seller: ₦{seller_gets:,.0f}\n"
            f"📍 {addr} | {landmark or 'No landmark'}",
            parse_mode="Markdown"
        )
        return

# ═══════════════════════════════════════════════════════
#  HELPER: SHOW INDUSTRY SELECTION
# ═══════════════════════════════════════════════════════
def show_industry_selection(message, user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO buyer_sessions (user_id, state) VALUES (?, 'BROWSING')", (user_id,))
    conn.commit()
    conn.close()
    bot.reply_to(message,
        "🏪 *OnTabs Marketplace*\n\nWhat are you looking for today?",
        reply_markup=industry_keyboard(),
        parse_mode="Markdown"
    )

def show_sellers_by_industry(message, user_id, industry):
    oil = (industry == "Oil")
    db  = OIL_DB if oil else MAIN_DB
    tbl_s = "oil_sellers" if oil else "sellers"
    tbl_p = "oil_products" if oil else "products"

    conn = get_conn(db)
    c = conn.cursor()
    if oil:
        c.execute(f"""SELECT s.seller_id, s.shop_name, s.bio, COUNT(p.id) as cnt
                      FROM {tbl_s} s JOIN {tbl_p} p ON s.seller_id = p.seller_id
                      WHERE s.is_approved = 1 GROUP BY s.seller_id ORDER BY s.shop_name""")
    else:
        c.execute(f"""SELECT s.seller_id, s.shop_name, s.bio,
                             GROUP_CONCAT(DISTINCT p.category) as cats, COUNT(p.id) as cnt
                      FROM {tbl_s} s JOIN {tbl_p} p ON s.seller_id = p.seller_id
                      WHERE s.is_approved = 1 GROUP BY s.seller_id ORDER BY s.shop_name""")
    shops = c.fetchall()
    conn.close()

    if not shops:
        bot.reply_to(message, f"😔 No {industry} sellers available right now. Check back soon!", reply_markup=ReplyKeyboardRemove())
        return

    icon = "🫙" if oil else "🧵"
    lines = [f"{icon} *{industry} Sellers on OnTabs*\n\n"]
    for shop in shops:
        sid, name, bio = shop[0], shop[1], shop[2]
        if oil:
            cnt = shop[3]
            lines.append(f"🔹 *{name}*\n   _{bio or 'No bio'}_\n   {cnt} product(s)\n")
        else:
            cats, cnt = shop[3], shop[4]
            lines.append(f"🔹 *{name}*\n   _{bio or 'No bio'}_\n   {cats or 'Various'} — {cnt} item(s)\n")

    lines.append("🔍 Type *search [name/product]* to find something specific\nor just type what you need 👇")

    conn2 = get_conn()
    c2 = conn2.cursor()
    c2.execute("INSERT OR REPLACE INTO buyer_sessions (user_id, state, industry) VALUES (?, 'BROWSING', ?)",
               (user_id, industry))
    conn2.commit()
    conn2.close()

    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

    # If oil, also show products
    if oil and shops:
        first_seller_id = shops[0][0]
        conn3 = get_conn(OIL_DB)
        c3 = conn3.cursor()
        c3.execute("SELECT id, name, price, stock, unit FROM oil_products WHERE seller_id = ?", (first_seller_id,))
        products = c3.fetchall()
        conn3.close()
        if products:
            lines2 = [f"🫙 *{shops[0][1]} — Available Products:*\n"]
            for p in products:
                sl = f"{p[3]} {p[4]}" if p[3] >= 0 else "In Stock"
                lines2.append(f"🔹 *{p[1]}* — ₦{p[2]:,}/{p[4]} | {sl}")
            lines2.append("\nWhich product do you want? Just type the name 👇")
            conn4 = get_conn()
            c4 = conn4.cursor()
            c4.execute("UPDATE buyer_sessions SET state = 'WAITING_FOR_OIL_PRODUCT', current_seller_id = ? WHERE user_id = ?",
                       (first_seller_id, user_id))
            conn4.commit()
            conn4.close()
            bot.send_message(user_id, "\n".join(lines2), parse_mode="Markdown")

def show_available_colors(message, category, gender, seller_id, not_found=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("""SELECT color, price, stock, unit FROM products
                 WHERE seller_id = ? AND category = ?
                 AND (gender = ? OR gender = 'Unisex') COLLATE NOCASE
                 ORDER BY color""", (seller_id, category, gender))
    rows = c.fetchall()
    conn.close()

    if not rows:
        bot.reply_to(message, f"😔 No *{category}* available right now.", parse_mode="Markdown")
        bot.send_message(ADMIN_ID, f"🚨 No {category} for {gender}\nBuyer: `{message.chat.id}`", parse_mode="Markdown")
        return

    lines = []
    if not_found:
        lines.append(f"🤔 No *{not_found}* found. We have:\n")
    else:
        label = "Ladies 👗" if gender == "Female" else "Men 👔" if gender == "Male" else "anyone 🎁"
        lines.append(f"✨ *{category}* for {label}:\n")

    for color, price, stock, unit in rows:
        sl = f"{stock} {unit}" if stock >= 0 else "In Stock"
        lines.append(f"🔹 {color} — ₦{price:,}/{unit} ({sl})")

    lines.append("\nWhich color? Just type it 👇")
    bot.reply_to(message, "\n".join(lines), parse_mode="Markdown", reply_markup=ReplyKeyboardRemove())

# ═══════════════════════════════════════════════════════
#  LAUNCH
# ═══════════════════════════════════════════════════════
if __name__ == "__main__":
    init_main_db()
    init_oil_db()
    migrate_buyer_profiles()

    scheduler.add_job(auto_release_check, 'interval', minutes=30)
    scheduler.start()
    reschedule_announcements()

    print("✅ OnTabs v6 is LIVE.")
    bot.infinity_polling()
