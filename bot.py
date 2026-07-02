import os
import sqlite3
import random
import string
import logging
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

def db():
    return sqlite3.connect(DB, check_same_thread=False)

def init():
    conn = db()
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
        conn = db()
        c = conn.cursor()
        c.execute('SELECT * FROM users WHERE user_id = ?', (uid,))
        r = c.fetchone()
        conn.close()
        if r:
            return (r[0], r[1], r[2], float(r[3]) if r[3] else 0, r[4], r[5], r[6])
        return None
    except:
        return None

def add_user(uid, username, first_name, ref=0):
    try:
        conn = db()
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
        print(f"❌ Error in add_user: {e}")
        return False

def update_balance(uid, amt):
    try:
        conn = db()
        c = conn.cursor()
        c.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (float(amt), uid))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"❌ Error updating balance: {e}")
        return False

def get_refs(uid):
    try:
        conn = db()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users WHERE referred_by = ?', (uid,))
        r = c.fetchone()[0]
        conn.close()
        return r
    except:
        return 0

def gen_code(amt, created_by):
    try:
        conn = db()
        c = conn.cursor()
        code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=10))
        c.execute('INSERT INTO codes (code, amount, created_by) VALUES (?, ?, ?)', (code, float(amt), created_by))
        conn.commit()
        conn.close()
        return code
    except:
        return None

def use_code(code, uid):
    try:
        conn = db()
        c = conn.cursor()
        c.execute('SELECT * FROM codes WHERE code = ? AND used = 0', (code,))
        r = c.fetchone()
        if r:
            amount = float(r[1])
            c.execute('UPDATE codes SET used = 1 WHERE code = ?', (code,))
            c.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, uid))
            conn.commit()
            conn.close()
            return True, amount
        conn.close()
        return False, 0
    except:
        return False, 0

def add_order(uid, plan):
    try:
        conn = db()
        c = conn.cursor()
        username = f"user_{uid}_{random.randint(100,999)}"
        password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
        c.execute('INSERT INTO orders (user_id, plan, username, password) VALUES (?, ?, ?, ?)',
                  (uid, plan, username, password))
        conn.commit()
        conn.close()
        return username, password
    except:
        return None, None

def get_orders():
    try:
        conn = db()
        c = conn.cursor()
        c.execute('SELECT * FROM orders WHERE status = "pending"')
        r = c.fetchall()
        conn.close()
        return r
    except:
        return []

def confirm_order(oid):
    try:
        conn = db()
        c = conn.cursor()
        c.execute('UPDATE orders SET status = "active" WHERE id = ?', (oid,))
        conn.commit()
        conn.close()
        return True
    except:
        return False

def get_total():
    try:
        conn = db()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM users')
        r = c.fetchone()[0]
        conn.close()
        return r
    except:
        return 0

def get_top_users(limit=10):
    try:
        conn = db()
        c = conn.cursor()
        c.execute('SELECT user_id, username, referrals, balance FROM users ORDER BY referrals DESC LIMIT ?', (limit,))
        r = c.fetchall()
        conn.close()
        return r
    except:
        return []

def get_total_balance():
    try:
        conn = db()
        c = conn.cursor()
        c.execute('SELECT SUM(balance) FROM users')
        r = c.fetchone()[0] or 0
        conn.close()
        return r
    except:
        return 0

def get_unused_codes():
    try:
        conn = db()
        c = conn.cursor()
        c.execute('SELECT COUNT(*) FROM codes WHERE used = 0')
        r = c.fetchone()[0]
        conn.close()
        return r
    except:
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
            balance = float(user[3]) if user[3] else 0
        else:
            balance = 0
        
        refs = get_refs(uid)
        balance_str = f"{balance:.2f}"
        
        keyboard = [
            [InlineKeyboardButton("🌐 HOSTING PLANS", callback_data='plans')],
            [InlineKeyboardButton("👤 PROFILE", callback_data='profile'), InlineKeyboardButton("🎁 REDEEM", callback_data='redeem')],
            [InlineKeyboardButton("👥 REFERRAL", callback_data='referral'), InlineKeyboardButton("🏆 LEADERBOARD", callback_data='leaderboard')],
            [InlineKeyboardButton("📊 SUPPORT", callback_data='support')]
        ]
        
        text = f"""✨ Welcome to Premium Hosting Bot!

👤 User ID: {uid}
💰 Balance: {balance_str} credits
👥 Referrals: {refs}

Select an option below:"""
        
        if is_message:
            await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
        else:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
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
                    balance = float(referrer[3]) if referrer[3] else 0
                    await context.bot.send_message(
                        int(ref),
                        f"🎉 New referral! @{username} joined!\n✅ +15 credits!\n💰 Balance: {balance:.2f}"
                    )
            except:
                pass
        
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
        
        text = "🌐 HOSTING PLANS\n\n"
        keyboard = []
        for k, v in PLANS.items():
            text += f"{v['name']} - {v['price']} credits\n"
            keyboard.append([InlineKeyboardButton(f"Buy {v['name']}", callback_data=f'buy_{k}')])
        keyboard.append([InlineKeyboardButton("⬅️ BACK", callback_data='back')])
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
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
        
        balance = float(user[3]) if user[3] else 0
        
        if balance < plan['price']:
            await query.edit_message_text(f"❌ Need {plan['price']}, have {balance:.2f}")
            return
        
        update_balance(uid, -plan['price'])
        username, password = add_order(uid, plan['name'])
        
        await context.bot.send_message(
            ADMIN_ID,
            f"🔔 NEW ORDER!\nUser: {uid}\nPlan: {plan['name']}\nUsername: {username}\nPassword: {password}"
        )
        await query.edit_message_text(f"✅ {plan['name']} purchased!\n⏳ Admin will activate within 24h.")
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
        balance = float(user[3]) if user[3] else 0
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='back')]]
        await query.edit_message_text(
            f"👤 PROFILE\n\nID: {uid}\nBalance: {balance:.2f}\nReferrals: {refs}",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        print(f"❌ Error in profile: {e}")

# ===== REDEEM =====
async def redeem(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='back')]]
    await query.edit_message_text("🎁 REDEEM\n\nSend: /redeem CODE", reply_markup=InlineKeyboardMarkup(keyboard))

async def redeem_command(update, context):
    try:
        if not context.args:
            await update.message.reply_text("❌ Usage: /redeem CODE")
            return
        
        code = context.args[0].upper()
        uid = update.effective_user.id
        
        # Check if code exists
        conn = db()
        c = conn.cursor()
        c.execute('SELECT * FROM codes WHERE code = ? AND used = 0', (code,))
        result = c.fetchone()
        conn.close()
        
        if not result:
            await update.message.reply_text("❌ Invalid or already used code!")
            return
        
        # Use the code
        success, amount = use_code(code, uid)
        
        if success:
            user = get_user(uid)
            balance = float(user[3]) if user[3] else 0
            await update.message.reply_text(
                f"✅ +{amount} credits!\n💰 Balance: {balance:.2f}\n\n💡 Buy hosting from the PLANS menu!"
            )
        else:
            await update.message.reply_text("❌ Error redeeming code!")
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
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='back')]]
        await query.edit_message_text(
            f"👥 REFERRAL\n\n🔗 {link}\n\n📊 Referrals: {refs}\n\n🎁 15 credits/referral\n🎁 25 bonus every 5 referrals",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    except Exception as e:
        print(f"❌ Error in referral: {e}")

# ===== LEADERBOARD =====
async def leaderboard(update, context):
    try:
        query = update.callback_query
        await query.answer()
        
        top = get_top_users(10)
        text = "🏆 TOP REFERRERS\n\n"
        if not top:
            text += "No users yet!"
        else:
            for i, u in enumerate(top, 1):
                medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
                name = f"@{u[1]}" if u[1] else f"User {u[0]}"
                text += f"{medal} {name} - {u[2]} referrals\n"
        
        keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='back')]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    except Exception as e:
        print(f"❌ Error in leaderboard: {e}")

# ===== SUPPORT =====
async def support(update, context):
    query = update.callback_query
    await query.answer()
    keyboard = [[InlineKeyboardButton("⬅️ BACK", callback_data='back')]]
    text = """📊 SUPPORT

❓ How to earn?
1. Refer friends → 15 credits
2. Every 5 referrals → 25 bonus
3. Redeem codes

❓ How to get hosting?
1. Earn 50+ credits
2. Buy a plan
3. Admin creates hosting

Commands:
/start - Main menu
/menu - Show menu
/redeem - Redeem code"""
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

# ===== ADMIN =====
async def admin_panel(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    
    pending = get_orders()
    total = get_total()
    keyboard = [
        [InlineKeyboardButton("🔑 Generate Code", callback_data='gen_code')],
        [InlineKeyboardButton("📊 Stats", callback_data='stats')],
        [InlineKeyboardButton("📦 Orders", callback_data='pending')]
    ]
    await update.message.reply_text(f"🛠️ ADMIN\nUsers: {total}\nPending: {len(pending)}", reply_markup=InlineKeyboardMarkup(keyboard))

async def admin_gen_code(update, context):
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Send: /gencode AMOUNT")

async def admin_stats(update, context):
    query = update.callback_query
    await query.answer()
    total = get_total()
    pending = len(get_orders())
    total_bal = float(get_total_balance()) if get_total_balance() else 0
    unused = get_unused_codes()
    await query.edit_message_text(f"📊 STATS\nUsers: {total}\nPending: {pending}\nBalance: {total_bal:.2f}\nUnused Codes: {unused}")

async def admin_pending(update, context):
    query = update.callback_query
    await query.answer()
    orders = get_orders()
    if not orders:
        await query.edit_message_text("No orders")
        return
    text = "📦 ORDERS\n\n"
    for o in orders:
        text += f"ID: {o[0]} | User: {o[1]} | {o[2]}\n"
    text += "\nConfirm: /confirm ID"
    await query.edit_message_text(text)

async def generate_code(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /gencode AMOUNT")
        return
    amount = float(context.args[0])
    code = gen_code(amount, ADMIN_ID)
    if code:
        await update.message.reply_text(f"✅ Code: {code}\nAmount: {amount}")
    else:
        await update.message.reply_text("❌ Error")

async def confirm_order_cmd(update, context):
    if update.effective_user.id != ADMIN_ID:
        return
    if not context.args:
        await update.message.reply_text("Usage: /confirm ID")
        return
    try:
        order_id = int(context.args[0])
        conn = db()
        c = conn.cursor()
        c.execute('SELECT user_id FROM orders WHERE id = ? AND status = "pending"', (order_id,))
        result = c.fetchone()
        conn.close()
        if not result:
            await update.message.reply_text("Order not found!")
            return
        confirm_order(order_id)
        await context.bot.send_message(result[0], "🎉 Hosting is now active!")
        await update.message.reply_text(f"✅ Order {order_id} confirmed!")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def gencode_direct(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    if not context.args:
        await update.message.reply_text("Usage: /gencode AMOUNT")
        return
    try:
        amount = float(context.args[0])
        code = gen_code(amount, ADMIN_ID)
        if code:
            await update.message.reply_text(f"✅ Code: {code}\nAmount: {amount}")
        else:
            await update.message.reply_text("❌ Error")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

async def stats_direct(update, context):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("❌ Unauthorized!")
        return
    total = get_total()
    pending = len(get_orders())
    total_bal = float(get_total_balance()) if get_total_balance() else 0
    unused = get_unused_codes()
    await update.message.reply_text(f"📊 STATS\nUsers: {total}\nPending: {pending}\nBalance: {total_bal:.2f}\nUnused Codes: {unused}")

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