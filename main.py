import os
import sqlite3
import threading
import time
import logging
from flask import Flask
import telebot
from telebot import types

# ---------------------------------------------------------
# 1. LOGGING & FLASK KEEP-ALIVE SERVER (FOR RENDER)
# ---------------------------------------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

web_app = Flask('')

@web_app.route('/')
def home():
    return "QR BOT IS ALIVE 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    web_app.run(host="0.0.0.0", port=port)

# ---------------------------------------------------------
# 2. BOT INITIALIZATION & DATABASE SETUP
# ---------------------------------------------------------
TOKEN = os.getenv("BOT_TOKEN", "8776609545:AAFaNsGk4kAsiOWPksVEDordtoYtt1Vv7sY")
bot = telebot.TeleBot(TOKEN)

conn = sqlite3.connect('bot_database.db', check_same_thread=False)
cursor = conn.cursor()

# Tables Creation
cursor.execute('''CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    balance REAL DEFAULT 0.0,
    banned INTEGER DEFAULT 0
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS qr_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    qr_file_id TEXT,
    price REAL DEFAULT 8.0,
    status TEXT DEFAULT 'AVAILABLE',
    claimed_by INTEGER
)''')

conn.commit()

# Main Owner Admin ID
MAIN_ADMINS = [5057266771]
for admin_id in MAIN_ADMINS:
    cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (admin_id,))
conn.commit()

def is_admin(user_id):
    cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    return cursor.fetchone() is not None

def register_user(user_id, username):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username or "Unknown"))
    conn.commit()

def is_banned(user_id):
    cursor.execute("SELECT banned FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row and row[0] == 1

user_states = {}

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        types.KeyboardButton("Get QR"),
        types.KeyboardButton("💰 Balance"),
        types.KeyboardButton("💸 Withdrawal"),
        types.KeyboardButton("📜 History"),
        types.KeyboardButton("🆘 Support")
    )
    return markup

# ---------------------------------------------------------
# 3. USER COMMAND HANDLERS
# ---------------------------------------------------------
@bot.message_handler(commands=['start'])
def start_cmd(message):
    uid = message.from_user.id
    register_user(uid, message.from_user.username)
    
    if is_banned(uid):
        bot.reply_to(message, "❌ You are banned from using this bot!")
        return
        
    start_msg = (
        "🚀 **Welcome to QR BOT!**\n\n"
        "Use the menu buttons below or commands to navigate:\n"
        "💰 Check Balance: `/balance`\n"
        "💸 Withdraw: `/withdrawal`"
    )
    bot.send_message(message.chat.id, start_msg, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@bot.message_handler(commands=['balance'])
def balance_cmd(message):
    uid = message.from_user.id
    if is_banned(uid): return
    register_user(uid, message.from_user.username)
    
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
    bal = cursor.fetchone()[0]
    
    msg = (
        "💰 **Your Balance**\n\n"
        f"₹{bal:.2f}\n\n"
        "💵 Reward per approved work: ₹8\n"
        "💸 Minimum withdrawal: ₹1"
    )
    bot.send_message(message.chat.id, msg, reply_markup=get_main_keyboard())

@bot.message_handler(commands=['withdrawal'])
def withdrawal_cmd(message):
    uid = message.from_user.id
    if is_banned(uid): return
    register_user(uid, message.from_user.username)
    
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
    bal = cursor.fetchone()[0]
    
    msg = (
        "💸 **Withdrawal**\n\n"
        f"💰 Current balance: ₹{bal:.2f}\n"
        "💸 Minimum withdrawal: ₹1\n\n"
        "Enter an amount of ₹1 or more:"
    )
    bot.send_message(message.chat.id, msg, reply_markup=get_main_keyboard())

# ---------------------------------------------------------
# 4. ADMIN PANEL & COMMANDS
# ---------------------------------------------------------
@bot.message_handler(commands=['admin'])
def admin_panel_cmd(message):
    if not is_admin(message.from_user.id): return

    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📤 Upload QR", callback_data="p_uploadqr"),
        types.InlineKeyboardButton("📊 Bot Stats", callback_data="p_stats")
    )
    bot.send_message(message.chat.id, "👑 **MAIN ADMIN CONTROL PANEL**", reply_markup=markup, parse_mode="Markdown")

@bot.callback_query_handler(func=lambda call: call.data.startswith("p_"))
def admin_callbacks(call):
    if not is_admin(call.from_user.id): return
    action = call.data
    chat_id = call.message.chat.id

    if action == "p_stats":
        cursor.execute("SELECT COUNT(*) FROM users")
        u_count = cursor.fetchone()[0]
        bot.send_message(chat_id, f"📊 **Total Users:** `{u_count}`", parse_mode="Markdown")
    elif action == "p_uploadqr":
        user_states[call.from_user.id] = "WAITING_QR_PHOTO"
        bot.send_message(chat_id, "📥 Please send the QR Code image:")

@bot.message_handler(content_types=['photo'])
def handle_photos(message):
    uid = message.from_user.id
    if not is_admin(uid): return
    
    if user_states.get(uid) == "WAITING_QR_PHOTO":
        file_id = message.photo[-1].file_id
        cursor.execute("INSERT INTO qr_tasks (qr_file_id, price) VALUES (?, ?)", (file_id, 8.0))
        conn.commit()
        task_id = cursor.lastrowid
        user_states[uid] = None
        bot.reply_to(message, f"✅ QR Code saved successfully! Task ID: `{task_id}`")

@bot.message_handler(commands=['newqr'])
def new_qr_cmd(message):
    if not is_admin(message.from_user.id): return
    cursor.execute("SELECT id FROM qr_tasks WHERE status = 'AVAILABLE' ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    if not row:
        bot.reply_to(message, "⚠️ No QR available! Upload one using `/admin` first.")
        return
        
    task_id = row[0]
    markup = types.InlineKeyboardMarkup()
    btn = types.InlineKeyboardButton("💳 Make Payment", callback_data=f"claim_qr_{task_id}")
    markup.add(btn)
    
    caption_text = (
        "💳 **NEW QR AVAILABLE**\n\n"
        "Tap 💳 **Make Payment** to claim the QR.\n"
        "Only the first eligible member can claim it."
    )
    
    cursor.execute("SELECT user_id FROM users WHERE banned = 0")
    users = cursor.fetchall()
    for u in users:
        try:
            bot.send_message(u[0], caption_text, reply_markup=markup, parse_mode="Markdown")
        except:
            pass
    bot.reply_to(message, "🚀 New QR alert sent to all users!")

# ---------------------------------------------------------
# 5. CLAIM QR CALLBACK (FIRST COME FIRST SERVE WITH PHOTO)
# ---------------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("claim_qr_"))
def claim_qr_callback(call):
    uid = call.from_user.id
    if is_banned(uid):
        bot.answer_callback_query(call.id, "❌ You are banned!", show_alert=True)
        return
        
    task_id = int(call.data.replace("claim_qr_", ""))
    cursor.execute("SELECT qr_file_id, status FROM qr_tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    
    if not row or row[0] is None or row[1] != 'AVAILABLE':
        bot.answer_callback_query(call.id, "❌ This QR has already been claimed by someone else!", show_alert=True)
    else:
        file_id = row[0]
        cursor.execute("UPDATE qr_tasks SET status = 'CLAIMED', claimed_by = ? WHERE id = ?", (uid, task_id))
        cursor.execute("UPDATE users SET balance = balance + 8.0 WHERE user_id = ?", (uid,))
        conn.commit()
        
        bot.answer_callback_query(call.id, "🎉 Success! You claimed this QR.", show_alert=False)
        bot.send_photo(call.message.chat.id, file_id, caption="✅ **QR Claimed Successfully!**\n₹8 added to your balance.", parse_mode="Markdown")

# ---------------------------------------------------------
# 6. BUTTON HANDLERS
# ---------------------------------------------------------
@bot.message_handler(func=lambda message: True)
def handle_text_buttons(message):
    uid = message.from_user.id
    if is_banned(uid): return
        
    register_user(uid, message.from_user.username)
    text = message.text.strip()

    if "Get QR" in text or "get qr" in text.lower():
        cursor.execute("SELECT id FROM qr_tasks WHERE status = 'AVAILABLE' ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            bot.reply_to(message, "There is no QR available right now.\nPlease wait for the next task.")
            return
        
        task_id = row[0]
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton("💳 Make Payment", callback_data=f"claim_qr_{task_id}")
        markup.add(btn)
        
        caption_text = (
            "💳 **NEW QR AVAILABLE**\n\n"
            "Tap 💳 **Make Payment** to claim the QR.\n"
            "Only the first eligible member can claim it."
        )
        bot.send_message(message.chat.id, caption_text, reply_markup=markup, parse_mode="Markdown")

    elif "Balance" in text or "balance" in text.lower():
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
        bal = cursor.fetchone()[0]
        msg = (
            "💰 **Your Balance**\n\n"
            f"₹{bal:.2f}\n\n"
            "💵 Reward per approved work: ₹8\n"
            "💸 Minimum withdrawal: ₹1"
        )
        bot.reply_to(message, msg)

    elif "Withdrawal" in text or "withdrawal" in text.lower():
        cursor.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
        bal = cursor.fetchone()[0]
        msg = (
            "💸 **Withdrawal**\n\n"
            f"💰 Current balance: ₹{bal:.2f}\n"
            "💸 Minimum withdrawal: ₹1\n\n"
            "Enter an amount of ₹1 or more:"
        )
        bot.reply_to(message, msg)

    elif "History" in text or "history" in text.lower():
        cursor.execute("SELECT COUNT(*) FROM qr_tasks WHERE claimed_by = ? AND status = 'CLAIMED'", (uid,))
        succ = cursor.fetchone()[0]
        
        msg = (
            "📊 **MY HISTORY**\n\n"
            f"✅ Success: {succ}\n"
            "❌ Failed: 0\n"
            "⏳ Expired: 0\n"
            "⏳ Pending: 0\n\n"
            "📜 **RECENT ACTIVITY**\n"
            "-------------------------\n"
            "No recent activity."
        )
        bot.reply_to(message, msg, parse_mode="Markdown")

    elif "Support" in text or "support" in text.lower():
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton("🆘 Contact Support", url="https://t.me/Dictator_0771")
        markup.add(btn)
        bot.send_message(message.chat.id, "🆘 **Support**\n\nIf you need help, contact our support team:", reply_markup=markup, parse_mode="Markdown")

# ---------------------------------------------------------
# 7. MAIN EXECUTION WITH AUTOMATIC SESSION RESET
# ---------------------------------------------------------
if __name__ == "__main__":
    server_thread = threading.Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()
    
    print("Clearing old session and starting bot...")
    try:
        bot.remove_webhook(drop_pending_updates=True)
        time.sleep(2)
    except Exception as e:
        print(f"Notice: {e}")

    print("Bot starting polling...")
    bot.infinity_polling(skip_pending=True)

