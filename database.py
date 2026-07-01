import sqlite3
import datetime
import random
import string
from datetime import timedelta

conn = sqlite3.connect('bot.db', check_same_thread=False)
cursor = conn.cursor()

# Users table
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

# Redeem codes table
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

# Transactions table
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

# Hosting requests table (for manual activation)
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

# ---- User Functions ----

def add_user(user_id, username, first_name, referred_by=0):
    cursor.execute('INSERT OR IGNORE INTO users (user_id, username, first_name, referred_by) VALUES (?, ?, ?, ?)',
                   (user_id, username, first_name, referred_by))
    conn.commit()

def get_user(user_id):
    cursor.execute('SELECT * FROM users WHERE user_id = ?', (user_id,))
    return cursor.fetchone()

def update_balance(user_id, amount):
    cursor.execute('UPDATE users SET balance = balance + ? WHERE user_id = ?', (amount, user_id))
    conn.commit()
    add_transaction(user_id, 'credit' if amount > 0 else 'debit', amount, 'Balance update')

def add_transaction(user_id, type, amount, description):
    cursor.execute('INSERT INTO transactions (user_id, type, amount, description) VALUES (?, ?, ?, ?)',
                   (user_id, type, amount, description))
    conn.commit()

def get_referral_count(user_id):
    cursor.execute('SELECT COUNT(*) FROM users WHERE referred_by = ?', (user_id,))
    return cursor.fetchone()[0]

# ---- Referral Bonus ----

def process_referral(referrer_id):
    # Add 15 credits per referral
    update_balance(referrer_id, 15)
    
    # Check if referral count is multiple of 5 for bonus
    count = get_referral_count(referrer_id)
    if count % 5 == 0:
        update_balance(referrer_id, 25)
        return 15, 25  # referral bonus + bonus
    return 15, 0

# ---- Redeem Codes ----

def generate_redeem_code(amount, created_by):
    code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))
    cursor.execute('INSERT INTO redeem_codes (code, amount, created_by) VALUES (?, ?, ?)',
                   (code, amount, created_by))
    conn.commit()
    return code

def redeem_code(code, user_id):
    cursor.execute('SELECT * FROM redeem_codes WHERE code = ? AND is_used = 0', (code,))
    result = cursor.fetchone()
    if result:
        cursor.execute('UPDATE redeem_codes SET is_used = 1, used_by = ?, used_at = CURRENT_TIMESTAMP WHERE code = ?',
                       (user_id, code))
        update_balance(user_id, result[1])
        conn.commit()
        return True, result[1]
    return False, 0

# ---- Hosting Requests (Manual) ----

def create_hosting_request(user_id, plan_name):
    import random, string
    username = f"user_{user_id}_{random.randint(100,999)}"
    password = ''.join(random.choices(string.ascii_letters + string.digits, k=12))
    
    cursor.execute('''
        INSERT INTO hosting_requests (user_id, plan_name, username, password)
        VALUES (?, ?, ?, ?)
    ''', (user_id, plan_name, username, password))
    conn.commit()
    return username, password

def get_pending_requests():
    cursor.execute('SELECT * FROM hosting_requests WHERE status = "pending"')
    return cursor.fetchall()

def confirm_hosting_request(request_id):
    cursor.execute('UPDATE hosting_requests SET status = "active" WHERE id = ?', (request_id,))
    conn.commit()

# ---- Stats ----

def get_total_users():
    cursor.execute('SELECT COUNT(*) FROM users')
    return cursor.fetchone()[0]

def get_top_referrers(limit=10):
    cursor.execute('''
        SELECT user_id, username, referral_count, balance 
        FROM users 
        ORDER BY referral_count DESC 
        LIMIT ?
    ''', (limit,))
    return cursor.fetchall()
