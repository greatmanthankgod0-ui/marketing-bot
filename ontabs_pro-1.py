import telebot
import sqlite3
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler

# ─────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────
TOKEN = "8725049105:AAGgiumdIOvsrNb8H6glLGEV0xg60v69mqk"
bot = telebot.TeleBot(TOKEN)
DB = "ontabs_pro.db"

# ─────────────────────────────────────────
#  DATABASE
# ─────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS businesses (
        owner_id INTEGER PRIMARY KEY,
        name TEXT DEFAULT NULL,
        account TEXT DEFAULT NULL,
        opening TEXT DEFAULT NULL,
        closing TEXT DEFAULT NULL,
        group_id INTEGER DEFAULT NULL,
        discount_enabled INTEGER DEFAULT 0,
        messages INTEGER DEFAULT 0,
        total_earned REAL DEFAULT 0.0,
        delivery_states TEXT DEFAULT NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER,
        name TEXT,
        price REAL,
        stock INTEGER DEFAULT -1,
        discount_price REAL DEFAULT NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER,
        customer_id INTEGER,
        name TEXT,
        location TEXT,
        total_buys INTEGER DEFAULT 0,
        stars INTEGER DEFAULT 0,
        secret_command TEXT DEFAULT NULL,
        last_seen TEXT DEFAULT NULL,
        UNIQUE(owner_id, customer_id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER,
        customer_id INTEGER,
        product TEXT,
        price REAL,
        timestamp TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS states (
        user_id INTEGER PRIMARY KEY,
        role TEXT DEFAULT NULL,
        step TEXT DEFAULT NULL,
        owner_id INTEGER DEFAULT NULL,
        temp TEXT DEFAULT NULL
    )''')

    conn.commit()
    conn.close()

# ─────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────
def get_conn():
    return sqlite3.connect(DB)

def get_business(owner_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM businesses WHERE owner_id=?", (owner_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        register_business(owner_id)
        return get_business(owner_id)
    return {
        "owner_id": row[0], "name": row[1], "account": row[2],
        "opening": row[3], "closing": row[4], "group_id": row[5],
        "discount_enabled": row[6], "messages": row[7],
        "total_earned": row[8], "delivery_states": row[9]
    }

def register_business(owner_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR IGNORE INTO businesses (owner_id) VALUES (?)", (owner_id,))
    conn.commit()
    conn.close()

def update_business(owner_id, field, value):
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"UPDATE businesses SET {field}=? WHERE owner_id=?", (value, owner_id))
    conn.commit()
    conn.close()

def get_user_state(user_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT role, step, owner_id, temp FROM states WHERE user_id=?", (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return {"role": None, "step": None, "owner_id": None, "temp": None}
    return {"role": row[0], "step": row[1], "owner_id": row[2], "temp": row[3]}

def set_user_state(user_id, role=None, step=None, owner_id=None, temp=None):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO states (user_id, role, step, owner_id, temp) VALUES (?,?,?,?,?)",
              (user_id, role, step, owner_id, temp))
    conn.commit()
    conn.close()

def get_customer(owner_id, customer_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM customers WHERE owner_id=? AND customer_id=?", (owner_id, customer_id))
    row = c.fetchone()
    conn.close()
    if not row:
        return None
    return {
        "owner_id": row[1], "customer_id": row[2], "name": row[3],
        "location": row[4], "total_buys": row[5], "stars": row[6],
        "secret_command": row[7], "last_seen": row[8]
    }

def get_products(owner_id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT name, price, stock, discount_price FROM products WHERE owner_id=?", (owner_id,))
    rows = c.fetchall()
    conn.close()
    return rows

def add_or_update_product(owner_id, name, price, stock=-1):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id FROM products WHERE owner_id=? AND name=?", (owner_id, name))
    existing = c.fetchone()
    if existing:
        c.execute("UPDATE products SET price=?, stock=? WHERE owner_id=? AND name=?",
                  (price, stock, owner_id, name))
    else:
        c.execute("INSERT INTO products (owner_id, name, price, stock) VALUES (?,?,?,?)",
                  (owner_id, name, price, stock))
    conn.commit()
    conn.close()

def format_product_list(owner_id, show_discount=False):
    products = get_products(owner_id)
    if not products:
        return None
    text = ""
    for name, price, stock, discount_price in products:
        stock_label = " ❌ OUT OF STOCK" if stock == 0 else (f" ({stock} left)" if stock > 0 else "")
        price_label = f"N{price:,.0f}"
        if show_discount and discount_price:
            price_label += f" → 🔥 N{discount_price:,.0f}"
        text += f"• {name} = {price_label}{stock_label}\n"
    return text

def get_profile_completion(owner_id):
    biz = get_business(owner_id)
    products = get_products(owner_id)
    fields = [biz["name"], biz["account"], biz["opening"], biz["closing"], biz["delivery_states"]]
    filled = sum(1 for f in fields if f) + (1 if products else 0)
    return int((filled / 6) * 100)

def calculate_stars(total_buys):
    if total_buys < 4:
        return 0
    elif total_buys < 12:
        return 1
    elif total_buys < 20:
        return 2
    elif total_buys < 28:
        return 3
    elif total_buys < 36:
        return 4
    else:
        cycle = (total_buys - 36) % 40
        if cycle < 8: return 5
        elif cycle < 16: return 4
        elif cycle < 24: return 3
        elif cycle < 32: return 2
        else: return 1

def get_star_display(stars):
    return "⭐" * stars if stars > 0 else ""

def generate_secret_command(customer_id, stars):
    return f"!deal{stars}x{str(customer_id)[-4:]}"

def record_buy(owner_id, customer_id, product, price):
    conn = get_conn()
    c = conn.cursor()
    c.execute("INSERT INTO orders (owner_id, customer_id, product, price, timestamp) VALUES (?,?,?,?,?)",
              (owner_id, customer_id, product, price, datetime.now().strftime("%Y-%m-%d %H:%M")))
    c.execute("UPDATE customers SET total_buys = total_buys + 1 WHERE owner_id=? AND customer_id=?",
              (owner_id, customer_id))
    c.execute("SELECT total_buys FROM customers WHERE owner_id=? AND customer_id=?", (owner_id, customer_id))
    total_buys = c.fetchone()[0]
    new_stars = calculate_stars(total_buys)
    secret = generate_secret_command(customer_id, new_stars) if new_stars >= 1 else None
    c.execute("UPDATE customers SET stars=?, secret_command=? WHERE owner_id=? AND customer_id=?",
              (new_stars, secret, owner_id, customer_id))
    c.execute("UPDATE businesses SET total_earned = total_earned + ? WHERE owner_id=?", (price, owner_id))
    c.execute("SELECT stock FROM products WHERE owner_id=? AND name=?", (owner_id, product))
    row = c.fetchone()
    if row and row[0] > 0:
        c.execute("UPDATE products SET stock = stock - 1 WHERE owner_id=? AND name=?", (owner_id, product))
    conn.commit()
    conn.close()
    return new_stars, total_buys, secret

def is_eligible(owner_id, location):
    biz = get_business(owner_id)
    if not biz["delivery_states"]:
        return True
    states = [s.strip().lower() for s in biz["delivery_states"].split(",")]
    return location.lower().strip() in states

def notify_admin(owner_id, text):
    try:
        bot.send_message(owner_id, text, parse_mode="Markdown")
    except:
        pass

# ─────────────────────────────────────────
#  OWNER ONBOARDING
# ─────────────────────────────────────────
def start_owner_onboarding(message):
    owner_id = message.chat.id
    register_business(owner_id)
    set_user_state(owner_id, role="owner", step="ask_name", owner_id=owner_id)
    bot.send_message(owner_id, (
        "Welcome to *ONTABS* 👋\n\n"
        "I'm your AI business assistant.\n"
        "I keep your business active, consistent "
        "and responsive — even when you're not.\n\n"
        "Let's get you set up real quick.\n\n"
        "*What's your business name?*"
    ), parse_mode="Markdown")

def handle_owner_onboarding(message, state):
    owner_id = message.chat.id
    step = state["step"]
    text = message.text.strip()

    if step == "ask_name":
        update_business(owner_id, "name", text)
        set_user_state(owner_id, role="owner", step="ask_opening", owner_id=owner_id)
        bot.send_message(owner_id, (
            f"Love it! ✅ *{text}* is officially on tabs.\n\n"
            f"What time do you *open* for business?\n"
            f"_(Example: 8:00 AM)_"
        ), parse_mode="Markdown")

    elif step == "ask_opening":
        update_business(owner_id, "opening", text)
        set_user_state(owner_id, role="owner", step="ask_closing", owner_id=owner_id)
        bot.send_message(owner_id, (
            f"Got it! ✅ Opening at *{text}*\n\n"
            f"What time do you *close?*\n"
            f"_(Example: 6:00 PM)_"
        ), parse_mode="Markdown")

    elif step == "ask_closing":
        update_business(owner_id, "closing", text)
        set_user_state(owner_id, role="owner", step="ask_account", owner_id=owner_id)
        bot.send_message(owner_id, (
            f"Perfect! ✅ Closing at *{text}*\n\n"
            f"Drop your *payment account number and bank name.*\n"
            f"_(Example: 8030840431 Palmpay)_"
        ), parse_mode="Markdown")

    elif step == "ask_account":
        update_business(owner_id, "account", text)
        set_user_state(owner_id, role="owner", step="ask_states", owner_id=owner_id)
        bot.send_message(owner_id, (
            f"Saved! ✅\n\n"
            f"Which *states* do you deliver to?\n"
            f"_(Example: Lagos, Abuja, Rivers)_\n\n"
            f"Customers outside these states won't be able to order "
            f"but I'll notify you — so you never miss a lead."
        ), parse_mode="Markdown")

    elif step == "ask_states":
        update_business(owner_id, "delivery_states", text)
        set_user_state(owner_id, role="owner", step="done", owner_id=owner_id)
        percent = get_profile_completion(owner_id)
        bot.send_message(owner_id, (
            f"✅ Delivering to: *{text}*\n\n"
            f"━━━━━━━━━━━━━━━\n"
            f"🚀 *{get_business(owner_id)['name']} is now LIVE on ONTABS!*\n"
            f"━━━━━━━━━━━━━━━\n\n"
            f"Profile: *{percent}% complete*\n\n"
            f"To go fully on tabs, add your products:\n"
            f"`/addproduct ProductName, Price, Stock`\n\n"
            f"_Example: /addproduct ONTABS Bot, 5000, 10_\n\n"
            f"Type /help to see everything I can do."
        ), parse_mode="Markdown")

# ─────────────────────────────────────────
#  CUSTOMER FLOW
# ─────────────────────────────────────────
def start_customer_flow(message, owner_id):
    customer_id = message.from_user.id
    biz = get_business(owner_id)
    customer = get_customer(owner_id, customer_id)

    # Returning customer
    if customer and customer["name"] and customer["location"]:
        name = customer["name"]
        set_user_state(customer_id, role="customer", step="browsing", owner_id=owner_id)
        list_text = format_product_list(owner_id)
        bot.send_message(customer_id, (
            f"Welcome back *{name}*! 👋\n\n"
            f"Great to see you again.\n"
            f"Here's what we've got:\n\n"
            f"{list_text if list_text else 'Products coming soon!'}\n"
            f"What would you like today?"
        ), parse_mode="Markdown")
        notify_admin(owner_id, f"🔔 Returning customer *{name}* is back!")
        return

    # New customer
    set_user_state(customer_id, role="customer", step="ask_name", owner_id=owner_id)
    bot.send_message(customer_id, (
        f"Hey there! 👋 Welcome to *{biz['name']}*\n\n"
        f"I'm here to help you with your order.\n\n"
        f"What's your name?"
    ), parse_mode="Markdown")

def handle_customer_flow(message, state):
    customer_id = message.from_user.id
    owner_id = state["owner_id"]
    step = state["step"]
    text = message.text.strip()
    biz = get_business(owner_id)

    if step == "ask_name":
        set_user_state(customer_id, role="customer", step="ask_location",
                      owner_id=owner_id, temp=text)
        bot.send_message(customer_id, (
            f"Nice to meet you *{text}*! 😊\n\n"
            f"Which *state* are you in?\n"
            f"_(This helps us confirm we can deliver to you)_"
        ), parse_mode="Markdown")

    elif step == "ask_location":
        name = state["temp"] or "there"
        now = datetime.now().strftime("%Y-%m-%d %H:%M")

        if is_eligible(owner_id, text):
            conn = get_conn()
            c = conn.cursor()
            c.execute('''INSERT OR IGNORE INTO customers 
                (owner_id, customer_id, name, location, last_seen) VALUES (?,?,?,?,?)''',
                (owner_id, customer_id, name, text, now))
            c.execute('''UPDATE customers SET name=?, location=?, last_seen=? 
                WHERE owner_id=? AND customer_id=?''',
                (name, text, now, owner_id, customer_id))
            conn.commit()
            conn.close()

            set_user_state(customer_id, role="customer", step="browsing", owner_id=owner_id)
            notify_admin(owner_id, (
                f"🔔 *New Customer!*\n\n"
                f"👤 {name}\n📍 {text}\n"
                f"✅ Eligible for delivery\n"
                f"🕐 {datetime.now().strftime('%H:%M')}"
            ))

            list_text = format_product_list(owner_id)
            bot.send_message(customer_id, (
                f"Great news *{name}*! We deliver to *{text}* ✅\n\n"
                f"Here's what we've got:\n\n"
                f"{list_text if list_text else 'Products coming soon!'}\n"
                f"What would you like to order?"
            ), parse_mode="Markdown")
        else:
            conn = get_conn()
            c = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M")
            c.execute('''INSERT OR IGNORE INTO customers 
                (owner_id, customer_id, name, location, last_seen) VALUES (?,?,?,?,?)''',
                (owner_id, customer_id, name, text, now))
            c.execute('''UPDATE customers SET name=?, location=?, last_seen=? 
                WHERE owner_id=? AND customer_id=?''',
                (name, text, now, owner_id, customer_id))
            conn.commit()
            conn.close()

            set_user_state(customer_id, role="customer", step="ineligible", owner_id=owner_id)
            notify_admin(owner_id, (
                f"🔔 *Missed Lead*\n\n"
                f"👤 {name}\n📍 {text}\n"
                f"❌ Outside delivery zone\n"
                f"💡 Consider expanding to {text}?\n"
                f"🕐 {datetime.now().strftime('%H:%M')}"
            ))
            bot.send_message(customer_id, (
                f"Sorry *{name}* 😔\n\n"
                f"We don't currently deliver to *{text}*.\n\n"
                f"I've let the team know you reached out.\n"
                f"They may get back to you if that changes! 🙏"
            ), parse_mode="Markdown")

    elif step == "browsing":
        handle_customer_browsing(message, state, text)

def handle_customer_browsing(message, state, text):
    customer_id = message.from_user.id
    owner_id = state["owner_id"]
    biz = get_business(owner_id)
    customer = get_customer(owner_id, customer_id)
    name = customer["name"] if customer else "there"
    text_lower = text.lower()

    # Check product match
    products = get_products(owner_id)
    for pname, price, stock, discount_price in products:
        if pname.lower() in text_lower or text_lower in pname.lower():
            if stock == 0:
                bot.send_message(customer_id, (
                    f"Sorry *{name}*, *{pname}* is out of stock right now 😔\n\n"
                    f"Want to check something else?"
                ), parse_mode="Markdown")
                notify_admin(owner_id, f"🔔 *{name}* asked about *{pname}* — out of stock.")
            else:
                bot.send_message(customer_id, (
                    f"Great choice *{name}*! 🔥\n\n"
                    f"*{pname}* = N{price:,.0f}\n"
                    f"{'📦 ' + str(stock) + ' units available' if stock > 0 else ''}\n\n"
                    f"💳 Send payment to:\n{biz['account']}\n\n"
                    f"Once done, send us a screenshot and your order will be confirmed! ✅"
                ), parse_mode="Markdown")
                notify_admin(owner_id, (
                    f"🛒 *Order Interest!*\n\n"
                    f"👤 {name} | 📍 {customer['location']}\n"
                    f"📦 {pname} — N{price:,.0f}\n"
                    f"🕐 {datetime.now().strftime('%H:%M')}\n\n"
                    f"To confirm: /confirmorder {customer_id}, {pname}, {price}"
                ))
            return

    if any(w in text_lower for w in ["pay", "account", "transfer", "payment"]):
        bot.send_message(customer_id, f"💳 Send payment to:\n{biz['account']}")
        return

    if any(w in text_lower for w in ["open", "hours", "close", "when", "time"]):
        bot.send_message(customer_id, f"⏰ We are open:\n{biz['opening']} — {biz['closing']}")
        return

    if any(w in text_lower for w in ["price", "how much", "cost", "list", "what"]):
        list_text = format_product_list(owner_id)
        bot.send_message(customer_id, (
            f"Here's everything we've got *{name}*:\n\n"
            f"{list_text if list_text else 'No products yet.'}\n"
            f"Just tell me what you'd like!"
        ), parse_mode="Markdown")
        return

    # Confused
    list_text = format_product_list(owner_id)
    bot.send_message(customer_id, (
        f"Can you be a bit more specific *{name}*? 🤔\n\n"
        f"Here's what we offer:\n\n"
        f"{list_text if list_text else 'No products listed yet.'}\n"
        f"Just tell me what you need!"
    ), parse_mode="Markdown")
    notify_admin(owner_id, (
        f"🔔 *Unresolved Message*\n\n"
        f"👤 {name}\n💬 {message.text}\n"
        f"🕐 {datetime.now().strftime('%H:%M')}"
    ))

# ─────────────────────────────────────────
#  COMMANDS
# ─────────────────────────────────────────
@bot.message_handler(commands=["start"])
def start(message):
    user_id = message.chat.id
    state = get_user_state(user_id)

    if state["role"] == "owner":
        biz = get_business(user_id)
        percent = get_profile_completion(user_id)
        bot.send_message(user_id, (
            f"Welcome back! 👋\n\n"
            f"*{biz['name']}* is on tabs.\n"
            f"Profile: *{percent}% complete*\n\n"
            f"Type /help to see all commands."
        ), parse_mode="Markdown")
        return

    if message.chat.type in ["group", "supergroup"]:
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT owner_id FROM businesses WHERE group_id=?", (message.chat.id,))
        row = c.fetchone()
        conn.close()
        if row:
            start_customer_flow(message, row[0])
            return

    start_owner_onboarding(message)

@bot.message_handler(commands=["help"])
def help_cmd(message):
    bot.send_message(message.chat.id, (
        "📋 *ONTABS PRO COMMANDS*\n\n"
        "*Update Your Business*\n"
        "/setname — Business name\n"
        "/setaccount — Payment account\n"
        "/setopen — Opening time\n"
        "/setclose — Closing time\n"
        "/setstates — Delivery states\n"
        "/setgroup — Register group\n\n"
        "*Products*\n"
        "/addproduct — Add product, price, stock\n"
        "/setstock — Update stock\n"
        "/setdiscount — Set starred buyer price\n"
        "/togglediscount — Enable/disable discounts\n"
        "/removediscount — Remove discount\n"
        "/repost — Post full price list\n\n"
        "*Orders*\n"
        "/confirmorder — Confirm a buyer order\n"
        "/buyers — View starred buyers\n\n"
        "*Stats*\n"
        "/stats — Full business stats\n"
        "/profile — View profile completion\n\n"
        "*Broadcast*\n"
        "/broadcast — Send message to group"
    ), parse_mode="Markdown")

@bot.message_handler(commands=["setname"])
def set_name(message):
    text = message.text.replace("/setname", "").strip()
    if not text:
        bot.reply_to(message, "Usage: /setname Your Business Name")
        return
    update_business(message.chat.id, "name", text)
    bot.reply_to(message, f"✅ Business name: *{text}*", parse_mode="Markdown")

@bot.message_handler(commands=["setaccount"])
def set_account(message):
    text = message.text.replace("/setaccount", "").strip()
    if not text:
        bot.reply_to(message, "Usage: /setaccount 1234567890 BankName")
        return
    update_business(message.chat.id, "account", text)
    bot.reply_to(message, f"✅ Account: {text}")

@bot.message_handler(commands=["setopen"])
def set_open(message):
    text = message.text.replace("/setopen", "").strip()
    if not text:
        bot.reply_to(message, "Usage: /setopen 8:00 AM")
        return
    update_business(message.chat.id, "opening", text)
    bot.reply_to(message, f"✅ Opening: {text}")

@bot.message_handler(commands=["setclose"])
def set_close(message):
    text = message.text.replace("/setclose", "").strip()
    if not text:
        bot.reply_to(message, "Usage: /setclose 6:00 PM")
        return
    update_business(message.chat.id, "closing", text)
    bot.reply_to(message, f"✅ Closing: {text}")

@bot.message_handler(commands=["setstates"])
def set_states(message):
    text = message.text.replace("/setstates", "").strip()
    if not text:
        bot.reply_to(message, "Usage: /setstates Lagos, Abuja, Rivers")
        return
    update_business(message.chat.id, "delivery_states", text)
    bot.reply_to(message, f"✅ Delivery states: *{text}*", parse_mode="Markdown")

@bot.message_handler(commands=["setgroup"])
def set_group(message):
    update_business(message.chat.id, "group_id", message.chat.id)
    bot.reply_to(message, "✅ Group registered for auto posts")

@bot.message_handler(commands=["profile"])
def view_profile(message):
    owner_id = message.chat.id
    biz = get_business(owner_id)
    products = get_products(owner_id)
    percent = get_profile_completion(owner_id)
    missing = []
    if not biz["name"]: missing.append("Business name")
    if not biz["account"]: missing.append("Payment account")
    if not biz["opening"]: missing.append("Opening time")
    if not biz["closing"]: missing.append("Closing time")
    if not biz["delivery_states"]: missing.append("Delivery states")
    if not products: missing.append("Products")
    text = (
        f"📊 *YOUR ONTABS PROFILE*\n\n"
        f"Business: {biz['name'] or 'Not set'}\n"
        f"Account: {biz['account'] or 'Not set'}\n"
        f"Hours: {(biz['opening'] or '?')} — {(biz['closing'] or '?')}\n"
        f"States: {biz['delivery_states'] or 'Not set'}\n"
        f"Products: {len(products)}\n\n"
        f"Completion: *{percent}%*\n"
    )
    if missing:
        text += "\n⚠️ *Still needed:*\n"
        for m in missing:
            text += f"• {m}\n"
    else:
        text += "\n✅ *Profile fully complete!*"
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=["addproduct"])
def add_product(message):
    text = message.text.replace("/addproduct", "").strip()
    if not text or "," not in text:
        bot.reply_to(message, "Usage: /addproduct ProductName, Price, Stock(optional)")
        return
    parts = text.split(",")
    name = parts[0].strip().lower()
    try:
        price = float(parts[1].strip().replace(",", ""))
    except:
        bot.reply_to(message, "❌ Invalid price.")
        return
    stock = -1
    if len(parts) >= 3:
        try:
            stock = int(parts[2].strip())
        except:
            stock = -1
    add_or_update_product(message.chat.id, name, price, stock)
    percent = get_profile_completion(message.chat.id)
    bot.reply_to(message, (
        f"✅ *{name}* = N{price:,.0f}"
        f"{' | Stock: ' + str(stock) if stock >= 0 else ''}\n\n"
        f"Profile: *{percent}% complete*"
    ), parse_mode="Markdown")

@bot.message_handler(commands=["setstock"])
def set_stock(message):
    text = message.text.replace("/setstock", "").strip()
    if not text or "," not in text:
        bot.reply_to(message, "Usage: /setstock ProductName, NewStock")
        return
    parts = text.split(",", 1)
    name = parts[0].strip().lower()
    try:
        stock = int(parts[1].strip())
    except:
        bot.reply_to(message, "❌ Stock must be a number.")
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE products SET stock=? WHERE owner_id=? AND name=?",
              (stock, message.chat.id, name))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"✅ *{name}* stock → {stock} units", parse_mode="Markdown")

@bot.message_handler(commands=["setdiscount"])
def set_discount(message):
    text = message.text.replace("/setdiscount", "").strip()
    if not text or "," not in text:
        bot.reply_to(message, "Usage: /setdiscount ProductName, DiscountPrice")
        return
    parts = text.split(",", 1)
    name = parts[0].strip().lower()
    try:
        discount = float(parts[1].strip().replace(",", ""))
    except:
        bot.reply_to(message, "❌ Invalid price.")
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE products SET discount_price=? WHERE owner_id=? AND name=?",
              (discount, message.chat.id, name))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"✅ Discount: *{name}* = N{discount:,.0f} for starred buyers", parse_mode="Markdown")

@bot.message_handler(commands=["removediscount"])
def remove_discount(message):
    name = message.text.replace("/removediscount", "").strip().lower()
    if not name:
        bot.reply_to(message, "Usage: /removediscount ProductName")
        return
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE products SET discount_price=NULL WHERE owner_id=? AND name=?",
              (message.chat.id, name))
    conn.commit()
    conn.close()
    bot.reply_to(message, f"✅ Discount removed from *{name}*", parse_mode="Markdown")

@bot.message_handler(commands=["togglediscount"])
def toggle_discount(message):
    biz = get_business(message.chat.id)
    new_val = 0 if biz["discount_enabled"] else 1
    update_business(message.chat.id, "discount_enabled", new_val)
    bot.reply_to(message, f"Discounts: *{'ENABLED 🔥' if new_val else 'DISABLED'}*", parse_mode="Markdown")

@bot.message_handler(commands=["repost"])
def repost(message):
    biz = get_business(message.chat.id)
    list_text = format_product_list(message.chat.id)
    if not list_text:
        bot.reply_to(message, "No products yet. Use /addproduct to add.")
        return
    bot.reply_to(message, (
        f"🛒 *{biz['name']} PRICE LIST*\n\n{list_text}"
        f"\n⏰ {biz['opening']} — {biz['closing']}"
        f"\n💳 {biz['account']}"
    ), parse_mode="Markdown")

@bot.message_handler(commands=["confirmorder"])
def confirm_order(message):
    text = message.text.replace("/confirmorder", "").strip()
    if not text or "," not in text:
        bot.reply_to(message, "Usage: /confirmorder CustomerID, ProductName, Price")
        return
    parts = text.split(",")
    try:
        customer_id = int(parts[0].strip())
        product = parts[1].strip().lower()
        price = float(parts[2].strip().replace(",", ""))
    except:
        bot.reply_to(message, "❌ Check format: CustomerID, ProductName, Price")
        return
    owner_id = message.chat.id
    customer = get_customer(owner_id, customer_id)
    if not customer:
        bot.reply_to(message, "❌ Customer not found.")
        return
    new_stars, total_buys, secret = record_buy(owner_id, customer_id, product, price)
    star_display = get_star_display(new_stars)
    name = customer["name"]
    reply = (
        f"✅ *Order Confirmed!*\n\n"
        f"👤 {name}\n📦 {product} — N{price:,.0f}\n"
        f"🛍 Total buys: {total_buys}\n"
        f"⭐ Stars: {star_display if star_display else 'None yet'}\n"
    )
    if new_stars >= 1 and secret:
        reply += f"\n🔐 Secret command: `{secret}`\nSend to {name} privately."
    bot.reply_to(message, reply, parse_mode="Markdown")
    try:
        msg = f"✅ Your *{product}* order is confirmed!\n\nThank you {name} 🙏"
        if star_display:
            msg += f"\n\nYour loyalty: {star_display}"
        if new_stars >= 1 and secret:
            msg += f"\n\n🎉 You've unlocked a secret deal!\nUse `{secret}` for your special price next time."
        bot.send_message(customer_id, msg, parse_mode="Markdown")
    except:
        pass

@bot.message_handler(commands=["stats"])
def get_stats(message):
    owner_id = message.chat.id
    biz = get_business(owner_id)
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM orders WHERE owner_id=?", (owner_id,))
    total_orders = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM customers WHERE owner_id=?", (owner_id,))
    total_customers = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM customers WHERE owner_id=? AND stars >= 1", (owner_id,))
    starred = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM products WHERE owner_id=? AND stock=0", (owner_id,))
    out_of_stock = c.fetchone()[0]
    conn.close()
    percent = get_profile_completion(owner_id)
    bot.reply_to(message, (
        f"📊 *{biz['name']} — ONTABS STATS*\n\n"
        f"👥 Customers: {total_customers}\n"
        f"💬 Messages: {biz['messages']}\n"
        f"📦 Orders: {total_orders}\n"
        f"💰 Earned: N{biz['total_earned']:,.0f}\n"
        f"⭐ Starred Buyers: {starred}\n"
        f"❌ Out of Stock: {out_of_stock}\n"
        f"📋 Profile: {percent}%\n\n"
        f"🕐 {datetime.now().strftime('%A, %d %B %Y %H:%M')}"
    ), parse_mode="Markdown")

@bot.message_handler(commands=["buyers"])
def view_buyers(message):
    conn = get_conn()
    c = conn.cursor()
    c.execute('''SELECT name, total_buys, stars, location FROM customers 
        WHERE owner_id=? AND stars >= 1 ORDER BY stars DESC''', (message.chat.id,))
    rows = c.fetchall()
    conn.close()
    if not rows:
        bot.reply_to(message, "No starred buyers yet.")
        return
    text = "⭐ *STARRED BUYERS*\n\n"
    for name, buys, stars, location in rows:
        text += f"{get_star_display(stars)} *{name}* — {buys} buys — {location}\n"
    bot.reply_to(message, text, parse_mode="Markdown")

@bot.message_handler(commands=["broadcast"])
def broadcast(message):
    biz = get_business(message.chat.id)
    text = message.text.replace("/broadcast", "").strip()
    if not text:
        bot.reply_to(message, "Usage: /broadcast Your message here")
        return
    if biz["group_id"]:
        try:
            bot.send_message(biz["group_id"], f"📢 *{biz['name']}*\n\n{text}", parse_mode="Markdown")
            bot.reply_to(message, "✅ Broadcast sent.")
        except:
            bot.reply_to(message, "❌ Could not reach group.")
    else:
        bot.reply_to(message, "No group registered. Use /setgroup in your group first.")

# ─────────────────────────────────────────
#  SECRET COMMAND
# ─────────────────────────────────────────
@bot.message_handler(func=lambda m: m.text and m.text.startswith("!deal"))
def handle_secret(message):
    customer_id = message.from_user.id
    state = get_user_state(customer_id)
    owner_id = state.get("owner_id") or message.chat.id
    biz = get_business(owner_id)
    customer = get_customer(owner_id, customer_id)
    if not customer or customer["secret_command"] != message.text.strip():
        bot.reply_to(message, "❌ Invalid command.")
        return
    stars = customer["stars"]
    if not biz["discount_enabled"]:
        bot.reply_to(message, f"Hey {get_star_display(stars)} member! Special pricing isn't active right now 🔥")
        return
    list_text = format_product_list(owner_id, show_discount=True)
    bot.reply_to(message, (
        f"🔐 *Exclusive Pricing — {get_star_display(stars)} Member*\n\n"
        f"{list_text if list_text else 'No products yet.'}\n"
        f"💳 {biz['account']}"
    ), parse_mode="Markdown")

# ─────────────────────────────────────────
#  MAIN HANDLER
# ─────────────────────────────────────────
@bot.message_handler(func=lambda m: True)
def handle_all(message):
    user_id = message.chat.id
    state = get_user_state(user_id)

    if state["role"] == "owner" and state["step"] not in ["done", None]:
        handle_owner_onboarding(message, state)
        return

    if state["role"] == "customer" and state["step"] not in ["done", "ineligible", None]:
        handle_customer_flow(message, state)
        return

    if state["role"] == "owner":
        biz = get_business(user_id)
        update_business(user_id, "messages", biz["messages"] + 1)
        text = message.text.lower()
        if any(w in text for w in ["hi", "hello", "hey"]):
            percent = get_profile_completion(user_id)
            bot.reply_to(message, (
                f"Hey! 👋 *{biz['name']}* is on tabs.\n"
                f"Profile: *{percent}% complete*\n\n"
                f"Type /help for commands."
            ), parse_mode="Markdown")
        else:
            bot.reply_to(message, "Type /help to see what I can do for you.")
        return

    start_owner_onboarding(message)

# ─────────────────────────────────────────
#  SCHEDULED POSTS
# ─────────────────────────────────────────
def auto_repost():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT owner_id, name, opening, closing, account, group_id FROM businesses WHERE group_id IS NOT NULL")
    rows = c.fetchall()
    conn.close()
    for owner_id, name, opening, closing, account, group_id in rows:
        list_text = format_product_list(owner_id)
        if not list_text:
            continue
        try:
            bot.send_message(group_id, (
                f"🛒 *{name} PRICE LIST*\n\n{list_text}"
                f"\n⏰ {opening} — {closing}\n💳 {account}"
            ), parse_mode="Markdown")
        except:
            pass

def opening_reminder():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT name, opening, closing, group_id FROM businesses WHERE group_id IS NOT NULL")
    rows = c.fetchall()
    conn.close()
    for name, opening, closing, group_id in rows:
        try:
            bot.send_message(group_id, f"🟢 *{name}* is now OPEN!\n⏰ {opening} — {closing}", parse_mode="Markdown")
        except:
            pass

def closing_reminder():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT name, group_id FROM businesses WHERE group_id IS NOT NULL")
    rows = c.fetchall()
    conn.close()
    for name, group_id in rows:
        try:
            bot.send_message(group_id, f"🔴 *{name}* is closing soon!\nPlace your orders now.", parse_mode="Markdown")
        except:
            pass

# ─────────────────────────────────────────
#  LAUNCH
# ─────────────────────────────────────────
init_db()

scheduler = BackgroundScheduler()
scheduler.add_job(auto_repost, 'cron', hour=8, minute=0)
scheduler.add_job(opening_reminder, 'cron', hour=8, minute=1)
scheduler.add_job(closing_reminder, 'cron', hour=17, minute=30)
scheduler.start()

print("ONTABS PRO is running")
bot.infinity_polling(timeout=60, long_polling_timeout=60)
