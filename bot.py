import os
import sqlite3
import random
import string
import logging
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# ===== SETUP =====
TOKEN = os.environ.get('BOT_TOKEN')
ADMIN_ID = int(os.environ.get('ADMIN_ID', '0'))

if not TOKEN or not ADMIN_ID:
    print("❌ Missing BOT_TOKEN or ADMIN_ID")
    exit(1)

logging.basicConfig(level=logging.INFO)
print("✅ Bot starting...")

# ===== DATABASE =====
DB = 'bot.db'

def get_db():
    conn = sqlite3.connect(DB, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init():
    conn = get_db()
    c = conn.cursor()
    
    c.execute('DROP TABLE IF EXISTS users')
    c.execute('DROP TABLE IF EXISTS codes')
    c.execute('DROP TABLE IF EXISTS orders')
    
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
    conn.commit()
    conn.close()
    print("✅ Database initialized!")

init()

# ===== DATABASE FUNCTIONS =====

def get_user(uid):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (uid,))
        r = c.fetchone()
        conn.close()
        if r:
            return dict(r)
        return None
    except Exception as e:
        print(f"❌ Error getting user: {e}")
        return None

def add_user(uid, username, first_name, ref=0):
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute('SELECT * FROM users WHERE user_id = ?', (uid,))
        existing = c.fetchone()
        
        if existing:
            conn.close()
            return False
        
        c.execute('INSERT INTO users (user_id, username, first_name, referred_by) VALUES (?, ?, ?, ?)',
                  (uid, username, first_name, ref))
        
        if ref and ref != uid:
            c.execute('UPDATE users SET balance = balance + 15, referrals = referrals + 1 WHERE user_id = ?', (ref,))
            c.execute('SELECT referrals FROM users WHERE user_id = ?', (ref,))
            count = c.fetchone()[0]
            if count % 5 == 0:
                c.execute('UPDATE users SET balance = balance + 25 WHERE user_id = ?', (ref,))
        
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        if conn:
            conn.close()
        print(f"❌ Error in add_user: {e}")
        return False

def update_balance(uid, amt):
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (float(amt), uid))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        if conn:
            conn.close()
        print(f"❌ Error updating balance: {e}")
        return False

def get_refs(uid):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users WHERE referred_by = ?', (uid,))
        r = c.fetchone()[0]
        conn.close()
        return r
    except Exception as e:
        print(f"❌ Error getting refs: {e}")
        return 0

def gen_code(amt, created_by):
    try:
        conn = get_db()
        c = conn.cursor()
        # New format: DYNO-X5C6-B3TB-CNB0
        parts = []
        for i in range(4):
            part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
            parts.append(part)
        code = f"DYNO-{parts[0]}-{parts[1]}-{parts[2]}"
        c.execute('INSERT INTO codes (code, amount, created_by) VALUES (?, ?, ?)', (code, float(amt), created_by))
        conn.commit()
        conn.close()
        return code
    except Exception as e:
        print(f"❌ Error generating code: {e}")
        return None

def use_code(code, uid):
    conn = None
    try:
        conn = get_db()
        c = conn.cursor()
        
        c.execute('SELECT * FROM codes WHERE code = ? AND used = 0', (code,))
        r = c.fetchone()
        
        if not r:
            conn.close()
            return False, 0
        
        amount = float(r[1])
        
        c.execute('UPDATE codes SET used = 1 WHERE code = ?', (code,))
        c.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, uid))
        
        conn.commit()
        conn.close()
        return True, amount
    except Exception as e:
        if conn:
            conn.close()
        print(f"❌ Error using code: {e}")
        return False, 0

def add_order(uid, plan):
    try:
        conn = get_db()
        c = conn.cursor()
        username = f"user_{uid}_{random.randint(100,999)}"
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        c.execute('INSERT INTO orders (user_id, plan, username, password) VALUES (?, ?, ?, ?)',
                  (uid, plan, username, password))
        conn.commit()
        conn.close()
        return username, password
    except Exception as e:
        print(f"❌ Error adding order: {e}")
        return None, None

def get_orders():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM orders WHERE status = "pending"')
        r = c.fetchall()
        conn.close()
        return r
    except Exception as e:
        print(f"❌ Error getting orders: {e}")
        return []

def confirm_order(oid):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('UPDATE orders SET status = "active" WHERE id = ?', (oid,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error confirming order: {e}")
        return False

def get_total():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users')
        r = c.fetchone()[0]
        conn.close()
        return r
    except Exception as e:
        print(f"❌ Error getting total: {e}")
        return 0

def get_top_users(limit=10):
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT user_id, username, referrals, balance FROM users ORDER BY referrals DESC LIMIT ?', (limit,))
        r = c.fetchall()
        conn.close()
        return r
    except Exception as e:
        print(f"❌ Error getting top users: {e}")
        return []

def get_total_balance():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT SUM(balance) FROM users')
        r = c.fetchone()[0] or 0
        conn.close()
        return r
    except Exception as e:
        print(f"❌ Error getting total balance: {e}")
        return 0

def get_unused_codes():
    try:
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM codes WHERE used = 0')
        r = c.fetchone()[0]
        conn.close()
        return r
    except Exception as e:
        print(f"❌ Error getting unused codes: {e}")
        return 0

# ===== PLANS =====
PLANS = {
    'starter': {'name': '🌱 Starter', 'price': 50},
    'pro': {'name': '🚀 Pro', 'price': 100},
    'business': {'name': '💼 Business', 'price': 200},
    'enterprise': {'name': '🏢 Enterprise', 'price': 500}
}

# ===== MAIN MENU =====
async def show_main_menu(update, context):
    try:
        if hasattr(update, 'message') and update.message:
            uid = update.message.from_user.id
            is_message = True
        else:
            query = update.callback_query
            uid = query.from_user.id
            await query.answer()
            is_message = False
        
        user = get_user(uid)
        if user:
            balance = float(user['balance']) if user['balance'] else 0
        else:
            balance = 0
        
        refs = get_refs(uid)
        balance_str = f"{balance:.2f}"
        
        # Colorful buttons with emojis
        keyboard = [
            [InlineKeyboardButton("🌐 HOSTING PLANS", callback_data='plans')],
            [
                InlineKeyboardButton("👤 PROFILE", callback_data='profile'),
                InlineKeyboardButton("🎁 REDEEM", callback_data='redeem')
            ],
            [
                InlineKeyboardButton("👥 REFERRAL", callback_data='referral'),
                InlineKeyboardButton("🏆 LEADERBOARD", callback_data='leaderboard')
            ],
            [InlineKeyboardButton("📊 SUPPORT", callback_data='support')]
        ]
        
        text = f"""✨ **Welcome to Premium Hosting Bot!** 

👤 User ID: `{uid}`
💰 Balance: `{balance_str}` Credits
👥 Referrals: `{refs}`

🔒 Your Invite Link:
`https://t.me/{context.bot.username}?start={uid}`

Select an option below:"""
        
        if is_message:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
        else:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        print(f"❌ Error in main menu: {e}")

# ===== START =====
async def start(update, context):
    try:
        uid = update.effective_user.id
        username = update.effective_user.username or ""
        first_name = update.effective_user.first_name or "User"
        ref = context.args[0] if context.args else 0
        
        if ref and int(ref) == uid:
            ref = 0
            await update.message.reply_text("⚠️ You cannot refer yourself!")
        
        existing = get_user(uid)
        if existing:
            await show_main_menu(update, context)
            return
        
        add_user(uid, username, first_name, int(ref) if ref else 0)
        
        if ref:
            try:
                referrer = get_user(int(ref))
                if referrer:
                    balance = float(referrer['balance']) if referrer['balance'] else 0
                    await context.bot.send_message(
                        int(ref),
                        f"🎉 **New Referral!**\n\n@{username} joined using your link!\n✅ +15 Credits!\n💰 Balance: {balance:.2f} Credits",
                        parse_mode='Markdown'
                    )
            except Exception as e:
                print(f"❌ Error notifying referrer: {e}")
        
        await show_main_menu(update, context)
    except Exception as e:
        print(f"❌ Error in start: {e}")
        await update.message.reply_text("⚠️ An error occurred. Please try again.")

# ===== MENU =====
async def menu(update, context):
    await show_main_menu(update, context)

# ===== BACK =====
async def back(update, context):
    await show_main_menu(update, context)

# ===== PLANS =====
async def show_plans(update, context):
    try:
        query = update.callback_query
        await query.answer()
        
        text = "🌐 **HOSTING PLANS**\n\n"
        keyboard = []
        for k, v in PLANS.items():
            text += f"{v['name']} - `{v['price']}` Credits\n"
            keyboard.append([InlineKeyboardButton(f"🛒 Buy {v['name']} - {v['price']} Credits", callback_data=f'buy_{k}')])
        keyboard.append([InlineKeyboardButton("⬅️ BACK TO MENU", callback_data='back')])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        print(f"❌ Error in plans: {e}")

# ===== BUY =====
async def buy_plan(update, context):
    try:
        query = update.callback_query
        await query.answer()
        
        uid = query.from_user.id
        key = query.data.split('_')[1]
        plan = PLANS[key]
        user = get_user(uid)
        
        if not user:
            await query.edit_message_text("❌ Please /start first!")
            return
        
        balance = float(user['balance']) if user['balance'] else 0
        
        if balance < plan['price']:
            await query.edit_message_text(f"❌ **Insufficient Balance!**\n\nNeed: `{plan['price']}` Credits\nHave: `{balance:.2f}` Credits\n\n💡 Earn more via referrals or redeem codes!", parse_mode='Markdown')
            return
        
        update_balance(uid, -plan['price'])
        username, password = add_order(uid, plan['name'])
        
        await context.bot.send_message(
            ADMIN_ID,
            f"🔔 **NEW ORDER!**\n\n👤 User: `{uid}`\n📦 Plan: {plan['name']}\n👤 Username: `{username}`\n🔑 Password: `{password}`\n\nConfirm: `/confirm ORDER_ID`",
            parse_mode='Markdown'
        )
        await query.edit_message_text(f"✅ **{plan['name']} Purchased!**\n\n⏳ Admin will activate within 24h.\n📌 Order ID: #{uid}", parse_mode='Markdown')
    except Exception as e:
        print(f"❌ Error in buy: {e}")

# ===== PROFILE =====
async def profile(update, context):
    try:
        query = update.callback_query
        await query.answer()
        
        uid = query.from_user.id
        user = get_user(uid)
        if not user:
            await query.edit_message_text("❌ Please /start first!")
            return
        
        refs = get_refs(uid)
        balance = float(user['balance']) if user['balance'] else 0
        keyboard = [[InlineKeyboardButton("⬅️ BACK TO MENU", callback_data='back')]]
        
        text = f"""👤 **USER PROFILE**

🆔 User ID: `{uid}`
📛 Username: @{user['username'] or 'N/A'}
💰 Balance: `{balance:.2f}` Credits
👥 Total Referrals: `{refs}`

📊 **Referral Progress:** {refs}/5 for bonus!"""
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        print(f"❌ Error in profile: {e}")

# ===== REDEEM =====
async def redeem(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("⬅️ BACK TO MENU", callback_data='back')]]
    await query.edit_message_text(
        "🎁 **REDEEM CODE**\n\nSend the code using:\n`/redeem DYNO-XXXX-XXXX-XXXX`\n\n💡 Codes are provided by admins during promotions!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def redeem_command(update, context):
    try:
        if not context.args:
            await update.message.reply_text(
                "❌ **Usage:** `/redeem DYNO-XXXX-XXXX-XXXX`\n\nExample: `/redeem DYNO-X5C6-B3TB-CNB0`",
                parse_mode='Markdown'
            )
            return
        
        code = context.args[0].upper()
        uid = update.effective_user.id
        
        user = get_user(uid)
        if not user:
            await update.message.reply_text("❌ Please /start first!")
            return
        
        success, amount = use_code(code, uid)
        
        if success:
            user = get_user(uid)
            balance = float(user['balance']) if user['balance'] else 0
            await update.message.reply_text(
                f"✅ **Redeem Successful!**\n\n💰 +`{amount}` Credits Added!\n💳 New Balance: `{balance:.2f}` Credits\n\n💡 Buy hosting from the PLANS menu!",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "❌ **Invalid Code!**\n\n• Code may be expired\n• Code may already be used\n• Please check and try again",
                parse_mode='Markdown'
            )
    except Exception as e:
        print(f"❌ Error in redeem: {e}")
        await update.message.reply_text("❌ Error! Please try again.")

# ===== REFERRAL =====
async def referral(update, context):
    try:
        query = update.callback_query
        await query.answer()
        
        uid = query.from_user.id
        link = f"https://t.me/{context.bot.username}?start={uid}"
        refs = get_refs(uid)
        keyboard = [[InlineKeyboardButton("⬅️ BACK TO MENU", callback_data='back')]]
        
        text = f"""👥 **REFERRAL PROGRAM**

🔗 **Your Invite Link:**
`{link}`

📊 **Your Referrals:** `{refs}`

🎁 **Rewards System:**
• `15` Credits per referral
• `25` Bonus Credits every 5 referrals
• Top referrers get exclusive rewards!

📢 Share your link and earn free hosting!"""
        
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        print(f"❌ Error in referral: {e}")

# ===== LEADERBOARD =====
async def leaderboard(update, context):
    try:
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
                text += f"{medal} {name}\n   👥 {u[2]} referrals | 💰 {u[3]:.0f} credits\n\n"
        
        keyboard = [[InlineKeyboardButton("⬅️ BACK TO MENU", callback_data='back')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    except Exception as e:
        print(f"❌ Error in leaderboard: {e}")

# ===== SUPPORT =====
async def support(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("⬅️ BACK TO MENU", callback_data='back')]]
    text = """📊 **SUPPORT CENTER**

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
/redeem - Redeem code"""
    
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

# ===== ADMIN =====
async def admin_panel(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ **Unauthorized!**", parse_mode='Markdown')
        return
    
    pending = get_orders()
    total = get_total()
    keyboard = [
        [InlineKeyboardButton("🔑 GENERATE CODE", callback_data='gen_code')],
        [InlineKeyboardButton("📊 STATISTICS", callback_data='stats')],
        [InlineKeyboardButton("📦 PENDING ORDERS", callback_data='pending')]
    ]
    await update.message.reply_text(
        f"🛠️ **ADMIN PANEL**\n\n👥 Users: `{total}`\n📦 Pending: `{len(pending)}`",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

async def admin_gen_code(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("🔑 **Generate Code**\n\nSend: `/gencode AMOUNT`\nExample: `/gencode 100`", parse_mode='Markdown')

async def admin_stats(update, context):
    query = update.callback_query
    await query.answer()
    total = get_total()
    pending = len(get_orders())
    total_bal = float(get_total_balance()) if get_total_balance() else 0
    unused = get_unused_codes()
    await query.edit_message_text(
        f"📊 **BOT STATISTICS**\n\n👥 Users: `{total}`\n📦 Pending: `{pending}`\n💰 Balance: `{total_bal:.2f}`\n🎁 Unused Codes: `{unused}`",
        parse_mode='Markdown'
    )

async def admin_pending(update, context):
    query = update.callback_query
    await query.answer()
    orders = get_orders()
    if not orders:
        await query.edit_message_text("📦 **No pending orders!**", parse_mode='Markdown')
        return
    text = "📦 **PENDING ORDERS**\n\n"
    for o in orders:
        text += f"🆔 Order: `{o[0]}`\n👤 User: `{o[1]}`\n📦 Plan: {o[2]}\n👤 Username: `{o[3]}`\n🔑 Password: `{o[4]}`\n\n"
    text += "To confirm: `/confirm ORDER_ID`"
    await query.edit_message_text(text, parse_mode='Markdown')

async def generate_code(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: `/gencode AMOUNT`\nExample: `/gencode 100`", parse_mode='Markdown')
        return
    amount = float(context.args[0])
    code = gen_code(amount, ADMIN_ID)
    if code:
        await update.message.reply_text(
            f"✅ **Code Generated!**\n\n🔑 Code: `{code}`\n💰 Amount: `{amount}` Credits\n\nShare with users:\n`/redeem {code}`",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("❌ Error generating code!")

async def confirm_order_cmd(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: `/confirm ORDER_ID`\nExample: `/confirm 1`", parse_mode='Markdown')
        return
    try:
        order_id = int(context.args[0])
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT user_id FROM orders WHERE id = ? AND status = "pending"', (order_id,))
        result = c.fetchone()
        conn.close()
        if not result:
            await update.message.reply_text("❌ Order not found or already confirmed!")
            return
        confirm_order(order_id)
        await context.bot.send_message(
            result[0],
            "🎉 **Your Hosting is Now ACTIVE!**\n\n📌 Login: https://infinityfree.net/control-panel\n🔑 Check your email for credentials\n\nThank you for choosing us! 🚀",
            parse_mode='Markdown'
        )
        await update.message.reply_text(f"✅ **Order {order_id} confirmed!** User notified.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def gencode_direct(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized!", parse_mode='Markdown')
        return
    if not context.args:
        await update.message.reply_text("❌ Usage: `/gencode AMOUNT`\nExample: `/gencode 100`", parse_mode='Markdown')
        return
    try:
        amount = float(context.args[0])
        code = gen_code(amount, ADMIN_ID)
        if code:
            await update.message.reply_text(
                f"✅ **Code Generated!**\n\n🔑 Code: `{code}`\n💰 Amount: `{amount}` Credits",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ Error generating code!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def stats_direct(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized!", parse_mode='Markdown')
        return
    total = get_total()
    pending = len(get_orders())
    total_bal = float(get_total_balance()) if get_total_balance() else 0
    unused = get_unused_codes()
    await update.message.reply_text(
        f"📊 **BOT STATISTICS**\n\n👥 Users: `{total}`\n📦 Pending: `{pending}`\n💰 Balance: `{total_bal:.2f}`\n🎁 Unused Codes: `{unused}`",
        parse_mode='Markdown'
    )

# ===== MAIN =====
def main():
    print("🚀 Starting bot...")
    app = Application.builder().token(TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("menu", menu))
    app.add_handler(CommandHandler("redeem", redeem_command))
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("gencode", gencode_direct))
    app.add_handler(CommandHandler("stats", stats_direct))
    app.add_handler(CommandHandler("confirm", confirm_order_cmd))
    
    app.add_handler(CallbackQueryHandler(show_plans, pattern='^plans$'))
    app.add_handler(CallbackQueryHandler(profile, pattern='^profile$'))
    app.add_handler(CallbackQueryHandler(redeem, pattern='^redeem$'))
    app.add_handler(CallbackQueryHandler(referral, pattern='^referral$'))
    app.add_handler(CallbackQueryHandler(leaderboard, pattern='^leaderboard$'))
    app.add_handler(CallbackQueryHandler(support, pattern='^support$'))
    app.add_handler(CallbackQueryHandler(back, pattern='^back$'))
    app.add_handler(CallbackQueryHandler(buy_plan, pattern='^buy_'))
    app.add_handler(CallbackQueryHandler(admin_gen_code, pattern='^gen_code$'))
    app.add_handler(CallbackQueryHandler(admin_stats, pattern='^stats$'))
    app.add_handler(CallbackQueryHandler(admin_pending, pattern='^pending$'))
    
    print("🤖 Bot is running!")
    app.run_polling()

if __name__ == "__main__":
    main()