import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from database import *
import os

TOKEN = os.getenv('BOT_TOKEN')
ADMIN_ID = int(os.getenv('ADMIN_ID', 123456789))

logging.basicConfig(level=logging.INFO)

# ---- HOSTING PLANS ----

PLANS = {
    'starter': {'name': 'Starter', 'price': 50, 'storage': '5GB', 'bandwidth': '50GB', 'domains': 1, 'days': 30},
    'pro': {'name': 'Pro', 'price': 100, 'storage': '20GB', 'bandwidth': '200GB', 'domains': 5, 'days': 30},
    'business': {'name': 'Business', 'price': 200, 'storage': '50GB', 'bandwidth': 'Unlimited', 'domains': 20, 'days': 30},
    'enterprise': {'name': 'Enterprise', 'price': 500, 'storage': '200GB', 'bandwidth': 'Unlimited', 'domains': 'Unlimited', 'days': 30}
}

# ---- START COMMAND ----

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    referred_by = context.args[0] if context.args else 0
    
    # Add user to database
    add_user(user.id, user.username, user.first_name, int(referred_by) if referred_by else 0)
    
    # If referred by someone, give referral bonus
    if referred_by:
        referrer_id = int(referred_by)
        referral_bonus, bonus = process_referral(referrer_id)
        
        # Notify referrer
        await context.bot.send_message(
            referrer_id,
            f"🎉 **New Referral!**\n"
            f"@{user.username or user.first_name} joined using your link!\n"
            f"💰 +{referral_bonus} credits\n"
            f"{'🎁 Bonus +25 credits for 5 referrals!' if bonus else ''}",
            parse_mode='Markdown'
        )
    
    # Main menu keyboard
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
        f"🏆 **Premium Hosting Services**\n\n"
        f"📊 **Your Stats:**\n"
        f"💰 Balance: `{balance}` credits\n"
        f"👥 Referrals: `{referrals}`\n\n"
        f"Select an option below 👇",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ---- HOSTING PLANS ----

async def show_plans(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    text = "🌐 **Available Hosting Plans**\n\n"
    keyboard = []
    
    for key, plan in PLANS.items():
        text += f"""
**{plan['name']}**
💾 {plan['storage']} Storage | 📡 {plan['bandwidth']} Bandwidth
🌍 {plan['domains']} Domains | 📅 {plan['days']} Days
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
            f"❌ **Insufficient Balance!**\n\n"
            f"Need: {plan['price']} credits\n"
            f"Have: {user[3]} credits\n\n"
            f"💡 Earn more credits via:\n"
            f"• Referring friends (15 credits each)\n"
            f"• Redeem codes from admins",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data='back')]]),
            parse_mode='Markdown'
        )
        return
    
    # Deduct credits
    update_balance(user_id, -plan['price'])
    
    # Create hosting request (manual activation)
    username, password = create_hosting_request(user_id, plan['name'])
    
    # Notify admin
    await context.bot.send_message(
        ADMIN_ID,
        f"🔔 **New Hosting Order!**\n\n"
        f"User: {user_id}\n"
        f"Plan: {plan['name']}\n"
        f"Username: `{username}`\n"
        f"Password: `{password}`\n\n"
        f"Create account at InfinityFree and reply:\n"
        f"`/confirm_{user_id}`",
        parse_mode='Markdown'
    )
    
    # Confirm to user
    await query.edit_message_text(
        f"✅ **{plan['name']} Plan Activated!**\n\n"
        f"💰 Credits deducted: {plan['price']}\n"
        f"📅 Duration: {plan['days']} days\n\n"
        f"⏳ **Admin will create your hosting account within 24 hours.**\n"
        f"You'll receive login details via this bot.\n\n"
        f"📌 **Order ID:** #{user_id}",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("📊 My Profile", callback_data='profile')]]),
        parse_mode='Markdown'
    )

# ---- PROFILE ----

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = get_user(query.from_user.id)
    if not user:
        await query.edit_message_text("❌ Please /start first!")
        return
    
    referrals = get_referral_count(user[0])
    
    text = f"""👤 **My Profile**

🆔 ID: `{user[0]}`
📛 Name: {user[2]}
💰 Balance: `{user[3]}` credits
👥 Referrals: `{referrals}`

**💻 Hosting Status:**
🔴 No active hosting (pending admin approval)

📊 You need `{50 - user[3] if user[3] < 50 else 0}` more credits for Starter plan
"""
    
    keyboard = [
        [InlineKeyboardButton("🔄 Refresh", callback_data='profile')],
        [InlineKeyboardButton("⬅️ Back", callback_data='back')]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ---- REDEEM ----

async def redeem(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🎁 **Redeem Code**\n\n"
        "Send the code like this:\n"
        "`/redeem YOURCODE`\n\n"
        "💡 Codes are provided by admins during promotions!",
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
            f"✅ **Success!**\n"
            f"Added `{amount}` credits!\n"
            f"💰 New balance: `{user[3]}` credits",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("❌ Invalid or already used code!")

# ---- REFERRAL ----

async def referral(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    link = f"https://t.me/{context.bot.username}?start={user_id}"
    referrals = get_referral_count(user_id)
    
    text = f"""👥 **Referral Program**

🔗 Your referral link:
`{link}`

📊 Your referrals: `{referrals}`

🎁 **Rewards:**
• `15` credits per referral
• `25` bonus credits every `5` referrals
• Top referrers get exclusive rewards!

📢 Share your link and earn credits for hosting!"""
    
    keyboard = [
        [InlineKeyboardButton("🏆 Leaderboard", callback_data='leaderboard')],
        [InlineKeyboardButton("⬅️ Back", callback_data='back')]
    ]
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode='Markdown'
    )

# ---- LEADERBOARD ----

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    top_users = get_top_referrers(10)
    text = "🏆 **Top Referrers**\n\n"
    
    for i, user in enumerate(top_users, 1):
        medal = ["🥇", "🥈", "🥉"][i-1] if i <= 3 else f"{i}."
        username = f"@{user[1]}" if user[1] else f"User {user[0]}"
        text += f"{medal} {username} - {user[2]} referrals (💰{user[3]} credits)\n"
    
    await query.edit_message_text(
        text,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back", callback_data='back')]]),
        parse_mode='Markdown'
    )

# ---- ADMIN COMMANDS ----

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⚠️ Unauthorized!")
        return
    
    pending = get_pending_requests()
    total_users = get_total_users()
    
    keyboard = [
        [InlineKeyboardButton("🔑 Generate Code", callback_data='gen_code')],
        [InlineKeyboardButton("📊 Stats", callback_data='stats')],
        [InlineKeyboardButton("📦 Pending Orders", callback_data='pending')],
        [InlineKeyboardButton("👥 Users", callback_data='users')]
    ]
    
    await update.message.reply_text(
        f"🛠️ **Admin Panel**\n\n"
        f"👥 Total Users: {total_users}\n"
        f"📦 Pending Orders: {len(pending)}",
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
        f"✅ **Code Generated!**\n"
        f"Code: `{code}`\n"
        f"Amount: `{amount}` credits\n\n"
        f"Share with users: `/redeem {code}`",
        parse_mode='Markdown'
    )

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    total_users = get_total_users()
    pending = len(get_pending_requests())
    
    cursor.execute('SELECT SUM(balance) FROM users')
    total_balance = cursor.fetchone()[0] or 0
    
    cursor.execute('SELECT COUNT(*) FROM redeem_codes WHERE is_used = 0')
    unused_codes = cursor.fetchone()[0]
    
    await update.message.reply_text(
        f"📊 **Bot Statistics**\n\n"
        f"👥 Total Users: {total_users}\n"
        f"💰 Total Balance: {total_balance} credits\n"
        f"📦 Pending Orders: {pending}\n"
        f"🎁 Unused Codes: {unused_codes}",
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
        text += f"ID: {p[0]} | User: {p[1]} | Plan: {p[2]} | Username: `{p[3]}`\n"
    
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
    
    # Get user details
    cursor.execute('SELECT user_id FROM hosting_requests WHERE id = ?', (order_id,))
    result = cursor.fetchone()
    
    if result:
        user_id = result[0]
        await context.bot.send_message(
            user_id,
            "🎉 **Your hosting account is now active!**\n\n"
            "📌 Login: https://infinityfree.net/control-panel\n"
            "🔑 Check your email for credentials\n\n"
            "Thank you for choosing us! 🚀",
            parse_mode='Markdown'
        )
        await update.message.reply_text(f"✅ Order {order_id} confirmed! User notified.")
    else:
        await update.message.reply_text("❌ Order not found!")

async def users_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    cursor.execute('SELECT user_id, username, balance, referral_count FROM users ORDER BY created_at DESC LIMIT 20')
    users = cursor.fetchall()
    
    text = "👥 **Recent Users**\n\n"
    for u in users:
        username = f"@{u[1]}" if u[1] else f"ID:{u[0]}"
        text += f"• {username} | 💰{u[2]} | 👥{u[3]}\n"
    
    await update.message.reply_text(text or "No users yet", parse_mode='Markdown')

# ---- BACK BUTTON ----

async def back(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    await start(update, context)

# ---- MAIN ----

def main():
    app = Application.builder().token(TOKEN).build()
    
    # User commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("redeem", redeem_command))
    
    # Admin commands
    app.add_handler(CommandHandler("admin", admin_panel))
    app.add_handler(CommandHandler("gencode", generate_code))
    app.add_handler(CommandHandler("confirm", confirm_order))
    
    # Callbacks
    app.add_handler(CallbackQueryHandler(show_plans, pattern='plans'))
    app.add_handler(CallbackQueryHandler(profile, pattern='profile'))
    app.add_handler(CallbackQueryHandler(redeem, pattern='redeem'))
    app.add_handler(CallbackQueryHandler(referral, pattern='referral'))
    app.add_handler(CallbackQueryHandler(leaderboard, pattern='leaderboard'))
    app.add_handler(CallbackQueryHandler(back, pattern='back'))
    app.add_handler(CallbackQueryHandler(buy_plan, pattern='^buy_'))
    app.add_handler(CallbackQueryHandler(stats, pattern='stats'))
    app.add_handler(CallbackQueryHandler(pending_orders, pattern='pending'))
    app.add_handler(CallbackQueryHandler(users_list, pattern='users'))
    app.add_handler(CallbackQueryHandler(generate_code, pattern='gen_code'))
    
    print("🤖 Hosting Bot is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
