import os
import sqlite3
import random
import string
import logging
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ===== SETUP =====
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '0'))

if not TOKEN or not ADMIN_ID:
    print("❌ Missing BOT_TOKEN or ADMIN_ID")
    exit(1)

logging.basicConfig(level=logging.INFO)

# ===== DATABASE =====
DB = 'bot.db'

def db():
    return sqlite3.connect(DB, check_same_thread=False)

def init():
    conn = db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        balance REAL DEFAULT 0,
        referrals INTEGER DEFAULT 0,
        referred_by INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS codes (
        code TEXT PRIMARY KEY,
        amount REAL,
        used INTEGER DEFAULT 0,
        created_by INTEGER,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        plan TEXT,
        username TEXT,
        password TEXT,
        status TEXT DEFAULT 'pending',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        type TEXT,
        amount REAL,
        description TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

init()

# ===== DATABASE FUNCTIONS =====

def get_user(uid):
    conn = db()
    c = conn.cursor()
    c.execute('SELECT * FROM users WHERE user_id = ?', (uid,))
    r = c.fetchone()
    conn.close()
    return r

def add_user(uid, username, first_name, ref=0):
    conn = db()
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (user_id, username, first_name, referred_by) VALUES (?, ?, ?, ?)',
              (uid, username, first_name, ref))
    if ref:
        c.execute('UPDATE users SET balance = balance + 15, referrals = referrals + 1 WHERE user_id = ?', (ref,))
        c.execute('SELECT referrals FROM users WHERE user_id = ?', (ref,))
        count = c.fetchone()[0]
        if count % 5 == 0:
            c.execute('UPDATE users SET balance = balance + 25 WHERE user_id = ?', (ref,))
    conn.commit()
    conn.close()

def update_balance(uid, amt):
    conn = db()
    c = conn.cursor()
    c.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amt, uid))
    conn.commit()
    conn.close()

def get_refs(uid):
    conn = db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users WHERE referred_by = ?', (uid,))
    r = c.fetchone()[0]
    conn.close()
    return r

def gen_code(amt, created_by):
    conn = db()
    c = conn.cursor()
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
    c.execute('INSERT INTO codes (code, amount, created_by) VALUES (?, ?, ?)', (code, amt, created_by))
    conn.commit()
    conn.close()
    return code

def use_code(code, uid):
    conn = db()
    c = conn.cursor()
    c.execute('SELECT * FROM codes WHERE code = ? AND used = 0', (code,))
    r = c.fetchone()
    if r:
        c.execute('UPDATE codes SET used = 1 WHERE code = ?', (code,))
        update_balance(uid, r[1])
        conn.commit()
        conn.close()
        return True, r[1]
    conn.close()
    return False, 0

def add_order(uid, plan):
    conn = db()
    c = conn.cursor()
    username = f"user_{uid}_{random.randint(100,999)}"
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
    c.execute('INSERT INTO orders (user_id, plan, username, password) VALUES (?, ?, ?, ?)',
              (uid, plan, username, password))
    conn.commit()
    conn.close()
    return username, password

def get_orders():
    conn = db()
    c = conn.cursor()
    c.execute('SELECT * FROM orders WHERE status = "pending"')
    r = c.fetchall()
    conn.close()
    return r

def confirm_order(oid):
    conn = db()
    c = conn.cursor()
    c.execute('UPDATE orders SET status = "active" WHERE id = ?', (oid,))
    conn.commit()
    conn.close()

def get_total():
    conn = db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM users')
    r = c.fetchone()[0]
    conn.close()
    return r

def get_top_users(limit=10):
    conn = db()
    c = conn.cursor()
    c.execute('''
        SELECT user_id, username, referrals, balance 
        FROM users 
        ORDER BY referrals DESC 
        LIMIT ?
    ''', (limit,))
    r = c.fetchall()
    conn.close()
    return r

def get_total_balance():
    conn = db()
    c = conn.cursor()
    c.execute('SELECT SUM(balance) FROM users')
    r = c.fetchone()[0] or 0
    conn.close()
    return r

def get_unused_codes():
    conn = db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM codes WHERE used = 0')
    r = c.fetchone()[0]
    conn.close()
    return r

# ===== PLANS =====
PLANS = {
    'starter': {'name': '🌱 Starter', 'price': 50, 'emoji': '🌱'},
    'pro': {'name': '🚀 Pro', 'price': 100, 'emoji': '🚀'},
    'business': {'name': '💼 Business', 'price': 200, 'emoji': '💼'},
    'enterprise': {'name': '🏢 Enterprise', 'price': 500, 'emoji': '🏢'}
}

# ===== MAIN MENU =====
async def main_menu(update, context):
    """Show main menu with premium buttons"""
    uid = update.effective_user.id
    user = get_user(uid)
    
    if not user:
        await update.message.reply_text("❌ Please /start first!")
        return
    
    balance = user[2]
    refs = get_refs(uid)
    username = update.effective_user.username or "User"
    
    # Format balance with 2 decimal places
    balance_str = f"{balance:.2f}"
    
    # Premium UI with emojis and layout
    keyboard = [
        [
            InlineKeyboardButton("🎬 HOSTING PLANS", callback_data='plans')
        ],
        [
            InlineKeyboardButton("👤 MY PROFILE", callback_data='profile'),
            InlineKeyboardButton("🎁 REDEEM", callback_data='redeem')
        ],
        [
            InlineKeyboardButton("👥 REFERRAL", callback_data='referral'),
            InlineKeyboardButton("🏆 LEADERBOARD", callback_data='leaderboard')
        ],
        [
            InlineKeyboardButton("📊 SUPPORT", callback_data='support')
        ]
    ]
    
    text = f"""✨ **Welcome to Premium Hosting Bot!** 

Get working hosting accounts instantly.

👤 User ID: `{uid}`
💰 Your Balance: `{balance_str}` Balance
👥 Referrals: `{refs}`

Select an option below to get started:"""

    # Check if called from command or callback
    if hasattr(update, 'message') and update.message:
        await update.message.reply_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )
    else:
        query = update.callback_query
        await query.edit_message_text(
            text,
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode='Markdown'
        )

# ===== START COMMAND =====
async def start(update, context):
    uid = update.effective_user.id
    username = update.effective_user.username or ""
    first_name = update.effective_user.first_name or "User"
    ref = context.args[0] if context.args else 0
    
    add_user(uid, username, first_name, int(ref) if ref else 0)
    
    # Notify referrer
    if ref:
        try:
            referrer_id = int(ref)
            msg = f"🎉 New referral! @{username or first_name} joined!\n+15 credits!"
            await context.bot.send_message(referrer_id, msg)
        except:
            pass
    
    await main_menu(update, context)

# ===== MENU COMMAND =====
async def menu(update, context):
    """/menu command"""
    await main_menu(update, context)

# ===== BACK BUTTON =====
async def back(update, context):
    """Back to main menu"""
    query = update.callback_query
    await query.answer()
    await main_menu(update, context)

# ===== PLANS =====
async def show_plans(update, context):
    query = update.callback_query
    await query.answer()
    
    text = "🌐 **HOSTING PLANS**\n\n"
    keyboard = []
    
    for k, v in PLANS.items():
        text += f"""{v['emoji']} **{v['name']}**
💳 Price: `{v['price']}` credits
📅 Duration: 30 days
━━━━━━━━━━━━━━━━\n\n"""
        keyboard.append([InlineKeyboardButton(f"{v['emoji']} Buy {v['name']} - {v['price']} credits", callback_data=f'buy_{k}')])
    
    keyboard.append([InlineKeyboardButton("⬅️ BACK", callback_data='back')])
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def buy_plan(update, context):
    query = update.callback_query
    await query.answer()
    
    uid = query.from_user.id
    key = query.data.split('_')[1]
    plan = PLANS[key]
    user = get_user(uid)
    
    if not user:
        await query.edit_message_text("❌ Please /start first!")
        return
    
    if user[2] < plan['price']:
        await query.edit_message_text(
            f"❌ **Insufficient Balance!**\n\n"
            f"Need: `{plan['price']}` credits\n"
            f"Have: `{user[2]:.2f}` credits\n\n"
            f"💡 Earn more via referrals or redeem codes!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ BACK", callback_data='back')]]),
            parse_mode='Markdown'
        )
        return
    
    # Deduct credits
    update_balance(uid, -plan['price'])
    username, password = add_order(uid, plan['name'])
    
    # Notify admin
    await context.bot.send_message(
        ADMIN_ID,
        f"🔔 **NEW ORDER!**\n\n"
        f"👤 User: {uid}\n"
        f"📦 Plan: {plan['name']}\n"
        f"👤 Username: `{username}`\n"
        f"🔑 Password: `{password}`\n\n"
        f"Confirm: `/confirm ORDER_ID`",
        parse_mode='Markdown'
    )
    
    await query.edit_message_text(
        f"✅ **{plan['name']} Plan Activated!**\n\n"
        f"💰 Credits Used: `{plan['price']}`\n"
        f"📅 Duration: 30 Days\n\n"
        f"⏳ Admin will create your hosting within 24 hours.\n"
        f"You'll receive login details here.",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📊 MY PROFILE", callback_data='profile')]]),
        parse_mode='Markdown'
    )

# ===== PROFILE =====
async def profile(update, context):
    query = update.callback_query
    await query.answer()
    
    uid = query.from_user.id
    user = get_user(uid)
    
    if not user:
        await query.edit_message_text("❌ Please /start first!")
        return
    
    refs = get_refs(uid)
    balance_str = f"{user[2]:.2f}"
    
    keyboard = [
        [InlineKeyboardButton("🔄 REFRESH", callback_data='profile')],
        [InlineKeyboardButton("⬅️ BACK", callback_data='back')]
    ]
    
    text = f"""👤 **MY PROFILE**

🆔 User ID: `{uid}`
📛 Name: {user[1] or 'N/A'}
💰 Balance: `{balance_str}` credits
👥 Total Referrals: `{refs}`

**💻 Hosting Status:**
⏳ Pending Admin Approval

📊 Referral Progress: {refs}/5 for bonus!"""
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ===== REDEEM =====
async def redeem(update, context):
    query = update.callback_query
    await query.answer()
    
    keyboard = [
        [InlineKeyboardButton("⬅️ BACK", callback_data='back')]
    ]
    
    await query.edit_message_text(
        f"""🎁 **REDEEM CODE**

Enter your redeem code using:
`/redeem YOURCODE`

💡 Codes are provided by admins during promotions!
📌 Format: /redeem ABC123XYZ""",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def redeem_command(update, context):
    if not context.args:
        await update.message.reply_text(
            "❌ **Usage:** `/redeem CODE`\n\nExample: `/redeem ABC123XYZ`",
            parse_mode='Markdown'
        )
        return
    
    code = context.args[0].upper()
    uid = update.effective_user.id
    
    success, amount = use_code(code, uid)
    
    if success:
        user = get_user(uid)
        await update.message.reply_text(
            f"✅ **Redeem Successful!**\n\n"
            f"💰 +`{amount}` credits added!\n"
            f"📊 New Balance: `{user[2]:.2f}` credits",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            "❌ **Invalid Code!**\n\n"
            "• Code may be expired\n"
            "• Code may already be used\n"
            "• Please check and try again",
            parse_mode='Markdown'
        )

# ===== REFERRAL =====
async def referral(update, context):
    query = update.callback_query
    await query.answer()
    
    uid = query.from_user.id
    link = f"https://t.me/{context.bot.username}?start={uid}"
    refs = get_refs(uid)
    
    text = f"""👥 **REFERRAL PROGRAM**

🔗 **Your Referral Link:**
`{link}`

📊 **Your Referrals:** `{refs}`

🎁 **Rewards System:**
• `15` credits per referral
• `25` bonus credits every 5 referrals
• Top referrers get exclusive rewards!

📢 Share your link and earn free hosting!"""
    
    keyboard = [
        [InlineKeyboardButton("📋 COPY LINK", callback_data='copy_link')],
        [InlineKeyboardButton("⬅️ BACK", callback_data='back')]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ===== LEADERBOARD =====
async def leaderboard(update, context):
    query = update.callback_query
    await query.answer()
    
    top = get_top_users(10)
    text = "🏆 **TOP REFERRERS**\n\n"
    
    if not top:
        text += "No users yet! Be the first! 🚀"
    else:
        for i, u in enumerate(top, 1):
            medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
            name = f"@{u[1]}" if u[1] else f"User {u[0]}"
            text += f"{medal} {name}\n"
            text += f"   👥 {u[2]} referrals | 💰 {u[3]:.0f} credits\n\n"
    
    keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='back')]]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ===== SUPPORT =====
async def support(update, context):
    query = update.callback_query
    await query.answer()
    
    text = """📊 **SUPPORT**

❓ **How to earn credits?**
1. Refer friends → 15 credits each
2. Every 5 referrals → 25 bonus credits
3. Redeem promo codes

❓ **How to get hosting?**
1. Earn 50+ credits
2. Buy a plan from PLANS menu
3. Admin creates hosting for you

❓ **Need help?**
Contact admin: @Free_hostingbyreferbot

🛠️ **Commands:**
/start - Main menu
/menu - Show menu
/redeem - Redeem code
/profile - Check balance

💡 Tip: Share your referral link everywhere!"""
    
    keyboard = [
        [InlineKeyboardButton("⬅️ BACK", callback_data='back')]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ===== COPY LINK =====
async def copy_link(update, context):
    query = update.callback_query
    await query.answer("📋 Link copied to clipboard! (Tap and hold to copy)", show_alert=True)

# ===== ADMIN COMMANDS =====
async def admin_panel(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ **Unauthorized!**", parse_mode='Markdown')
        return
    
    pending = get_orders()
    total = get_total()
    total_bal = get_total_balance()
    unused = get_unused_codes()
    
    keyboard = [
        [InlineKeyboardButton("🔑 GENERATE CODE", callback_data='gen_code')],
        [InlineKeyboardButton("📊 STATISTICS", callback_data='stats')],
        [InlineKeyboardButton("📦 PENDING ORDERS", callback_data='pending')],
        [InlineKeyboardButton("👥 USERS", callback_data='users')]
    ]
    
    text = f"""🛠️ **ADMIN PANEL**

👥 Total Users: `{total}`
💰 Total Balance: `{total_bal:.2f}` credits
📦 Pending Orders: `{len(pending)}`
🎁 Unused Codes: `{unused}`

Select an option below:"""
    
    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def generate_code(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ **Usage:** `/gencode AMOUNT`\n\nExample: `/gencode 100`",
            parse_mode='Markdown'
        )
        return
    
    amount = float(context.args[0])
    code = gen_code(amount, ADMIN_ID)
    
    await update.message.reply_text(
        f"✅ **Code Generated!**\n\n"
        f"🔑 Code: `{code}`\n"
        f"💰 Amount: `{amount}` credits\n\n"
        f"Share with users:\n`/redeem {code}`",
        parse_mode='Markdown'
    )

async def stats(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    
    total = get_total()
    pending = len(get_orders())
    total_bal = get_total_balance()
    unused = get_unused_codes()
    
    await update.message.reply_text(
        f"""📊 **BOT STATISTICS**

👥 Total Users: `{total}`
💰 Total Balance: `{total_bal:.2f}` credits
📦 Pending Orders: `{pending}`
🎁 Unused Codes: `{unused}`

📅 Last Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}""",
        parse_mode='Markdown'
    )

async def pending_orders(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    
    orders = get_orders()
    
    if not orders:
        await update.message.reply_text("📦 **No pending orders!**", parse_mode='Markdown')
        return
    
    text = "📦 **PENDING ORDERS**\n\n"
    for o in orders:
        text += f"🆔 Order: `{o[0]}`\n"
        text += f"👤 User: `{o[1]}`\n"
        text += f"📦 Plan: {o[2]}\n"
        text += f"👤 Username: `{o[3]}`\n"
        text += f"🔑 Password: `{o[4]}`\n"
        text += "━━━━━━━━━━━━━━━━\n\n"
    
    text += "To confirm: `/confirm ORDER_ID`"
    
    await update.message.reply_text(text, parse_mode='Markdown')

async def confirm_order(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    
    if not context.args:
        await update.message.reply_text(
            "❌ **Usage:** `/confirm ORDER_ID`\n\nExample: `/confirm 1`",
            parse_mode='Markdown'
        )
        return
    
    order_id = int(context.args[0])
    
    # Get user_id before confirming
    conn = db()
    c = conn.cursor()
    c.execute('SELECT user_id FROM orders WHERE id = ? AND status = "pending"', (order_id,))
    result = c.fetchone()
    conn.close()
    
    if not result:
        await update.message.reply_text("❌ Order not found or already confirmed!")
        return
    
    user_id = result[0]
    confirm_order(order_id)
    
    # Notify user
    await context.bot.send_message(
        user_id,
        "🎉 **Your hosting is now ACTIVE!**\n\n"
        "📌 Login: https://infinityfree.net/control-panel\n"
        "🔑 Check your email for login credentials\n\n"
        "Thank you for choosing us! 🚀",
        parse_mode='Markdown'
    )
    
    await update.message.reply_text(f"✅ **Order {order_id} confirmed!** User notified.")

async def users_list(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    
    conn = db()
    c = conn.cursor()
    c.execute('SELECT user_id, username, first_name, balance, referrals FROM users ORDER BY created_at DESC LIMIT 20')
    users = c.fetchall()
    conn.close()
    
    if not users:
        await update.message.reply_text("No users yet!")
        return
    
    text = "👥 **RECENT USERS**\n\n"
    for u in users:
        name = u[2] or u[1] or f"User {u[0]}"
        text += f"• {name}\n"
        text += f"  🆔 {u[0]} | 💰 {u[3]:.0f} | 👥 {u[4]}\n\n"
    
    await update.message.reply_text(text, parse_mode='Markdown')

# ===== MAIN =====
def main():
    app = Application.builder().token(TOKEN).build()
    
    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("redeem", redeem_command))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("gencode", generate_code))
    app.add_handler(CommandHandler("confirm", confirm_order))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(show_plans, pattern='^plans$'))
    app.add_handler(CallbackQueryHandler(profile, pattern='^profile$'))
    app.add_handler(CallbackQueryHandler(redeem, pattern='^redeem$'))
    app.add_handler(CallbackQueryHandler(referral, pattern='^referral$'))
    app.add_handler(CallbackQueryHandler(leaderboard, pattern='^leaderboard$'))
    app.add_handler(CallbackQueryHandler(support, pattern='^support$'))
    app.add_handler(CallbackQueryHandler(back, pattern='^back$'))
    app.add_handler(CallbackQueryHandler(copy_link, pattern='^copy_link$'))
    app.add_handler(CallbackQueryHandler(buy_plan, pattern='^buy_'))
    app.add_handler(CallbackQueryHandler(stats, pattern='^stats$'))
    app.add_handler(CallbackQueryHandler(pending_orders, pattern='^pending$'))
    app.add_handler(CallbackQueryHandler(users_list, pattern='^users$'))
    app.add_handler(CallbackQueryHandler(generate_code, pattern='^gen_code$'))
    
    print("🤖 Premium Hosting Bot is running!")
    app.run_polling()

if __name__ == "__main__":
    main()
