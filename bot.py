import logging
import os
import sqlite3
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ===== CONFIGURATION =====
TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', 0))

if not TOKEN:
    print("❌ ERROR: BOT_TOKEN not set in environment variables!")
    exit(1)

if not ADMIN_ID:
    print("❌ ERROR: ADMIN_ID not set in environment variables!")
    exit(1)

logging.basicConfig(level=logging.INFO)

# ===== DATABASE SETUP =====
DB_PATH = 'bot.db'

def get_db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        balance REAL DEFAULT 0.0,
        referral_count INTEGER DEFAULT 0,
        referred_by INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS redeem_codes (
        code TEXT PRIMARY KEY,
        amount REAL,
        used_by INTEGER DEFAULT NULL,
        used_at TEXT DEFAULT NULL,
        created_by INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        is_used INTEGER DEFAULT 0
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT,
        amount REAL,
        description TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    cursor.execute('''
    CREATE TABLE IF NOT EXISTS hosting_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        plan_name TEXT,
        username TEXT,
        password TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    ''')
    
    conn.commit()
    conn.close()

# Initialize database
init_db()

# ===== DATABASE FUNCTIONS =====

def add_user(user_id, username, first_name, referred_by=0):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username, first_name, referred_by) VALUES (?, ?, ?, ?)',
                   (user_id, username, first_name, referred_by))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    conn.close()
    return result

def update_balance(user_id, amount):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    conn.close()
    
    # Add transaction
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)',
                   (user_id, 'credit' if amount > 0 else 'debit', amount, 'Balance update'))
    conn.commit()
    conn.close()

def get_referral_count(user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ?', (user_id,))
    result = cursor.fetchone()[0]
    conn.close()
    return result

def process_referral(referrer_id):
    update_balance(referrer_id, 15)
    count = get_referral_count(referrer_id)
    bonus = 0
    if count % 5 == 0:
        update_balance(referrer_id, 25)
        bonus = 25
    return 15, bonus

def generate_redeem_code(amount, created_by):
    import random, string
    conn = get_db()
    cursor = conn.cursor()
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
    cursor.execute('INSERT INTO redeem_codes (code, amount, created_by) VALUES (?, ?, ?)',
                   (code, amount, created_by))
    conn.commit()
    conn.close()
    return code

def redeem_code(code, user_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM redeem_codes WHERE code = ? AND is_used = 0', (code,))
    result = cursor.fetchone()
    if result:
        cursor.execute('UPDATE redeem_codes SET is_used = 1, used_by = ?, used_at = CURRENT_TIMESTAMP WHERE code = ?',
                       (user_id, code))
        conn.commit()
        conn.close()
        update_balance(user_id, result[1])
        return True, result[1]
    conn.close()
    return False, 0

def create_hosting_request(user_id, plan_name):
    import random, string
    conn = get_db()
    cursor = conn.cursor()
    username = f"user_{user_id}_{random.randint(100,999)}"
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
    cursor.execute('''
        INSERT INTO hosting_requests (user_id, plan_name, username, password)
        VALUES (?, ?, ?, ?)
    ''', (user_id, plan_name, username, password))
    conn.commit()
    conn.close()
    return username, password

def get_pending_requests():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM hosting_requests WHERE status = "pending"')
    result = cursor.fetchall()
    conn.close()
    return result

def confirm_hosting_request(request_id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('UPDATE hosting_requests SET status = "active" WHERE id = ?', (request_id,))
    conn.commit()
    conn.close()

def get_total_users():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('SELECT COUNT(*) FROM users')
    result = cursor.fetchone()[0]
    conn.close()
    return result

def get_top_referrers(limit=10):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT user_id, username, referral_count, balance 
        FROM users 
        ORDER BY referral_count DESC 
        LIMIT ?
    ''', (limit,))
    result = cursor.fetchall()
    conn.close()
    return result

# ===== HOSTING PLANS =====

PLANS = {
    'starter': {'name': 'Starter', 'price': 50, 'storage': '5GB', 'bandwidth': '50GB', 'domains': 1, 'days': 30},
    'pro': {'name': 'Pro', 'price': 100, 'storage': '20GB', 'bandwidth': '200GB', 'domains': 5, 'days': 30},
    'business': {'name': 'Business', 'price': 200, 'storage': '50GB', 'bandwidth': 'Unlimited', 'domains': 20, 'days': 30},
    'enterprise': {'name': 'Enterprise', 'price': 500, 'storage': '200GB', 'bandwidth': 'Unlimited', 'domains': 'Unlimited', 'days': 30}
}

# ===== BOT COMMANDS =====

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referred_by = context.args[0] if context.args else 0
    
    add_user(user.id, user.username, user.first_name, int(referred_by) if referred_by else 0)
    
    if referred_by:
        referrer_id = int(referred_by)
        referral_bonus, bonus = process_referral(referrer_id)
        await context.bot.send_message(
            referrer_id,
            f"🎉 **New Referral!**\n"
            f"@{user.username or user.first_name} joined!\n"
            f"💰 +{referral_bonus} credits\n"
            f"{'🎁 Bonus +25 credits!' if bonus else ''}",
            parse_mode='Markdown'
        )
    
    keyboard = [
        [InlineKeyboardButton("🌐 HOSTING PLANS", callback_data='plans')],
        [InlineKeyboardButton("👤 MY PROFILE", callback_data='profile')],
        [InlineKeyboardButton("🎁 REDEEM CODE", callback_data='redeem')],
        [InlineKeyboardButton("👥 REFERRAL", callback_data='referral')],
        [InlineKeyboardButton("🏆 LEADERBOARD", callback_data='leaderboard')]
    ]
    
    user_data = get_user(user.id)
    balance = user_data[3] if user_data else 0
    referrals = get_referral_count(user.id)
    
    await update.message.reply_text(
        f"✨ **Welcome {user.first_name}!**\n\n"
        f"💰 Balance: `{balance}` credits\n"
        f"👥 Referrals: `{referrals}`\n\n"
        f"Select an option 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = "🌐 **Hosting Plans**\n\n"
    keyboard = []
    
    for key, plan in PLANS.items():
        text += f"""
**{plan['name']}**
💾 {plan['storage']} | 📡 {plan['bandwidth']}
🌍 {plan['domains']} domains | 📅 {plan['days']} days
💰 {plan['price']} credits
"""
        keyboard.append([InlineKeyboardButton(f"Buy {plan['name']} - {plan['price']} credits", callback_data=f'buy_{key}')])
    
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data='back')])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def buy_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    plan_key = query.data.split('_')[1]
    plan = PLANS[plan_key]
    user_id = query.from_user.id
    user = get_user(user_id)
    
    if not user:
        await query.edit_message_text("❌ Please /start first!")
        return
    
    if user[3] < plan['price']:
        await query.edit_message_text(
            f"❌ Need {plan['price']} credits, you have {user[3]}\n\n"
            f"💡 Earn via referrals or redeem codes!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data='back')]]),
            parse_mode='Markdown'
        )
        return
    
    update_balance(user_id, -plan['price'])
    username, password = create_hosting_request(user_id, plan['name'])
    
    await context.bot.send_message(
        ADMIN_ID,
        f"🔔 **New Order!**\n\n"
        f"User: {user_id}\n"
        f"Plan: {plan['name']}\n"
        f"Username: `{username}`\n"
        f"Password: `{password}`\n\n"
        f"Reply: `/confirm_{user_id}`",
        parse_mode='Markdown'
    )
    
    await query.edit_message_text(
        f"✅ **{plan['name']} Plan Purchased!**\n\n"
        f"💰 Credits: -{plan['price']}\n"
        f"⏳ Admin will create hosting within 24 hours.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📊 Profile", callback_data='profile')]]),
        parse_mode='Markdown'
    )

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = get_user(query.from_user.id)
    if not user:
        await query.edit_message_text("❌ Please /start first!")
        return
    
    referrals = get_referral_count(user[0])
    
    text = f"""👤 **Profile**

🆔 ID: `{user[0]}`
💰 Balance: `{user[3]}` credits
👥 Referrals: `{referrals}`

💻 Hosting: Pending admin approval
"""
    
    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data='back')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text(
        "🎁 **Redeem Code**\n\nSend: `/redeem CODE`",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data='back')]]),
        parse_mode='Markdown'
    )

async def redeem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Usage: `/redeem CODE`", parse_mode='Markdown')
        return
    
    code = context.args[0].upper()
    user_id = update.effective_user.id
    
    success, amount = redeem_code(code, user_id)
    
    if success:
        user = get_user(user_id)
        await update.message.reply_text(
            f"✅ Added `{amount}` credits!\n💰 New balance: `{user[3]}`",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("❌ Invalid or used code!")

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    link = f"https://t.me/{context.bot.username}?start={user_id}"
    referrals = get_referral_count(user_id)
    
    text = f"""👥 **Referral Program**

🔗 Your link:
`{link}`

📊 Referrals: `{referrals}`

🎁 Rewards:
• 15 credits per referral
• 25 bonus every 5 referrals"""
    
    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data='back')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    top = get_top_referrers(10)
    text = "🏆 **Top Referrers**\n\n"
    
    for i, u in enumerate(top, 1):
        medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
        name = f"@{u[1]}" if u[1] else f"User {u[0]}"
        text += f"{medal} {name} - {u[2]} referrals\n"
    
    keyboard = [[InlineKeyboardButton("⬅️ Back", callback_data='back')]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⚠️ Unauthorized!")
        return
    
    pending = get_pending_requests()
    total = get_total_users()
    
    keyboard = [
        [InlineKeyboardButton("🔑 Generate Code", callback_data='gen_code')],
        [InlineKeyboardButton("📊 Stats", callback_data='stats')],
        [InlineKeyboardButton("📦 Pending", callback_data='pending')]
    ]
    
    await update.message.reply_text(
        f"🛠️ **Admin**\n👥 {total} users\n📦 {len(pending)} pending",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def generate_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args:
        await update.message.reply_text("Usage: `/gencode AMOUNT`", parse_mode='Markdown')
        return
    
    amount = float(context.args[0])
    code = generate_redeem_code(amount, ADMIN_ID)
    await update.message.reply_text(
        f"✅ Code: `{code}`\nAmount: {amount} credits",
        parse_mode='Markdown'
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    total = get_total_users()
    pending = len(get_pending_requests())
    
    await update.message.reply_text(
        f"📊 **Stats**\n👥 {total} users\n📦 {pending} pending",
        parse_mode='Markdown'
    )

async def pending_orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    pending = get_pending_requests()
    if not pending:
        await update.message.reply_text("📦 No pending orders!")
        return
    
    text = "📦 **Pending Orders**\n\n"
    for p in pending:
        text += f"ID: {p[0]} | User: {p[1]} | Plan: {p[2]}\n"
    
    text += "\nTo confirm: `/confirm ORDER_ID`"
    await update.message.reply_text(text, parse_mode='Markdown')

async def confirm_order(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args:
        await update.message.reply_text("Usage: `/confirm ORDER_ID`", parse_mode='Markdown')
        return
    
    order_id = int(context.args[0])
    confirm_hosting_request(order_id)
    
    await update.message.reply_text(f"✅ Order {order_id} confirmed!")
    
    # Notify user
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT user_id FROM hosting_requests WHERE id = ?', (order_id,))
    result = cursor.fetchone()
    conn.close()
    
    if result:
        await context.bot.send_message(
            result[0],
            "🎉 **Hosting Active!**\nLogin: https://infinityfree.net\nCheck your email for credentials."
        )

async def back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)

# ===== MAIN =====

def main():
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("redeem", redeem_command))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("gencode", generate_code))
    app.add_handler(CommandHandler("confirm", confirm_order))
    
    app.add_handler(CallbackQueryHandler(show_plans, pattern='plans'))
    app.add_handler(CallbackQueryHandler(profile, pattern='profile'))
    app.add_handler(CallbackQueryHandler(redeem, pattern='redeem'))
    app.add_handler(CallbackQueryHandler(referral, pattern='referral'))
    app.add_handler(CallbackQueryHandler(leaderboard, pattern='leaderboard'))
    app.add_handler(CallbackQueryHandler(back, pattern='back'))
    app.add_handler(CallbackQueryHandler(buy_plan, pattern='^buy_'))
    app.add_handler(CallbackQueryHandler(stats, pattern='stats'))
    app.add_handler(CallbackQueryHandler(pending_orders, pattern='pending'))
    app.add_handler(CallbackQueryHandler(generate_code, pattern='gen_code'))
    
    print("🤖 Bot is running!")
    app.run_polling()

if __name__ == "__main__":
    main()
