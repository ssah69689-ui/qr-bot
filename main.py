import os
import sqlite3
import threading
import time
import logging
import urllib.request
from flask import Flask
import telebot
from telebot import types

# ---------------------------------------------------------
# 1. LOGGING & FLASK KEEP-ALIVE SERVER (FOR RENDER 24/7)
# ---------------------------------------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

web_app = Flask('')

@web_app.route('/')
def home():
    return "🚀 QR BOT IS ALIVE 24/7!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    web_app.run(host="0.0.0.0", port=port)

def self_ping_loop():
    """Prevents Render free tier from sleeping by self-pinging every 5 mins"""
    port = int(os.environ.get("PORT", 5000))
    url = f"http://127.0.0.1:{port}/"
    while True:
        time.sleep(300)
        try:
            urllib.request.urlopen(url)
            logging.info("Self-ping successful! Bot kept alive.")
        except Exception as e:
            logging.warning(f"Self-ping notice: {e}")

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
    status TEXT DEFAULT 'AVAILABLE'
)''')

cursor.execute('''CREATE TABLE IF NOT EXISTS submissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id INTEGER,
    user_id INTEGER,
    proof_file_id TEXT,
    status TEXT DEFAULT 'PENDING'
)''')

conn.commit()

# Main Owner Admin ID (PERMANENT ADMIN LOCK - NEVER REMOVED)
MAIN_ADMINS = [5057266771]
for admin_id in MAIN_ADMINS:
    cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (admin_id,))
conn.commit()

def is_admin(user_id):
    """Main Owner is ALWAYS Admin even if DB resets"""
    if user_id in MAIN_ADMINS:
        return True
    cursor.execute("SELECT user_id FROM admins WHERE user_id = ?", (user_id,))
    return cursor.fetchone() is not None

def register_user(user_id, username):
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user_id, username or "User"))
    conn.commit()

def is_banned(user_id):
    cursor.execute("SELECT banned FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row and row[0] == 1

user_states = {}

def setup_bot_menu_commands():
    try:
        commands = [
            types.BotCommand("start", "🚀 Start the bot"),
            types.BotCommand("balance", "💰 Check your balance"),
            types.BotCommand("withdrawal", "💸 Request a withdrawal"),
            types.BotCommand("users", "👥 View registered users"),
            types.BotCommand("ban", "🚫 Ban a user"),
            types.BotCommand("unban", "✅ Unban a user"),
            types.BotCommand("addadmin", "👑 Add a new admin"),
            types.BotCommand("removeadmin", "🗑️ Remove an admin"),
            types.BotCommand("broadcast", "📢 Broadcast a message"),
            types.BotCommand("broadcastphoto", "🖼️ Broadcast a photo"),
            types.BotCommand("uploadqr", "📩 Upload a QR code"),
            types.BotCommand("newqr", "🔄 Create and announce a new QR"),
            types.BotCommand("addbalance", "➕ Add balance to a user"),
            types.BotCommand("deductbalance", "➖ Deduct balance from a user")
        ]
        bot.set_my_commands(commands)
        logging.info("Bot menu overlay commands configured!")
    except Exception as e:
        logging.error(f"Error setting bot commands: {e}")

def get_main_keyboard():
    markup = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    markup.add(
        types.KeyboardButton("🎯 Get QR"),
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
        bot.reply_to(message, "❌ **You are banned from using this bot!**", parse_mode="Markdown")
        return
        
    start_msg = (
        "🚀 **WELCOME TO QR WORK BOT!** 🚀\n\n"
        "✨ Complete QR tasks & earn instant rewards!\n\n"
        "👇 **Choose an option from the menu below:**"
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
        "💰 **YOUR CURRENT BALANCE** 💰\n\n"
        f"💵 **Balance:** ₹{bal:.2f}\n"
        "🎁 **Reward per approved task:** ₹8.00\n"
        "💸 **Minimum Withdrawal:** ₹1.00"
    )
    bot.send_message(message.chat.id, msg, reply_markup=get_main_keyboard(), parse_mode="Markdown")

@bot.message_handler(commands=['withdrawal'])
def withdrawal_cmd(message):
    uid = message.from_user.id
    if is_banned(uid): return
    register_user(uid, message.from_user.username)
    
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (uid,))
    bal = cursor.fetchone()[0]
    
    msg = (
        "💸 **WITHDRAWAL REQUEST** 💸\n\n"
        f"💰 **Available Balance:** ₹{bal:.2f}\n"
        "📉 **Minimum Withdrawal:** ₹1.00\n\n"
        "Enter an amount of ₹1 or more:"
    )
    bot.send_message(message.chat.id, msg, reply_markup=get_main_keyboard(), parse_mode="Markdown")

# ---------------------------------------------------------
# 4. ADMIN MANAGEMENT COMMANDS
# ---------------------------------------------------------
@bot.message_handler(commands=['addadmin'])
def add_admin_cmd(message):
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Usage: `/addadmin <user_id>`\nExample: `/addadmin 123456789`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[1])
        cursor.execute("INSERT OR IGNORE INTO admins (user_id) VALUES (?)", (target_id,))
        conn.commit()
        bot.reply_to(message, f"👑 **User `{target_id}` has been promoted to Admin!**", parse_mode="Markdown")
        try:
            bot.send_message(target_id, "👑 **You have been appointed as an Admin by the Owner!**", parse_mode="Markdown")
        except:
            pass
    except ValueError:
        bot.reply_to(message, "❌ Invalid User ID!")

@bot.message_handler(commands=['removeadmin'])
def remove_admin_cmd(message):
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Usage: `/removeadmin <user_id>`\nExample: `/removeadmin 123456789`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[1])
        if target_id in MAIN_ADMINS:
            bot.reply_to(message, "❌ Cannot remove Main Owner Admin!")
            return
        cursor.execute("DELETE FROM admins WHERE user_id = ?", (target_id,))
        conn.commit()
        bot.reply_to(message, f"🗑️ **User `{target_id}` removed from Admin list.**", parse_mode="Markdown")
    except ValueError:
        bot.reply_to(message, "❌ Invalid User ID!")

@bot.message_handler(commands=['users'])
def users_cmd(message):
    if not is_admin(message.from_user.id): return
    cursor.execute("SELECT user_id, username, balance, banned FROM users")
    rows = cursor.fetchall()
    
    if not rows:
        bot.reply_to(message, "👥 No registered users yet.")
        return
        
    text = f"👥 **REGISTERED USERS ({len(rows)})**\n\n"
    for r in rows[:30]:
        status = "🔴 Banned" if r[3] else "🟢 Active"
        text += f"• `{r[0]}` | @{r[1]} | Balance: ₹{r[2]:.2f} | {status}\n"
    bot.send_message(message.chat.id, text, parse_mode="Markdown")

@bot.message_handler(commands=['ban'])
def ban_cmd(message):
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Usage: `/ban <user_id>`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[1])
        cursor.execute("UPDATE users SET banned = 1 WHERE user_id = ?", (target_id,))
        conn.commit()
        bot.reply_to(message, f"🚫 **User `{target_id}` has been banned.**", parse_mode="Markdown")
    except ValueError:
        bot.reply_to(message, "❌ Invalid User ID!")

@bot.message_handler(commands=['unban'])
def unban_cmd(message):
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) < 2:
        bot.reply_to(message, "⚠️ Usage: `/unban <user_id>`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[1])
        cursor.execute("UPDATE users SET banned = 0 WHERE user_id = ?", (target_id,))
        conn.commit()
        bot.reply_to(message, f"✅ **User `{target_id}` has been unbanned.**", parse_mode="Markdown")
    except ValueError:
        bot.reply_to(message, "❌ Invalid User ID!")

@bot.message_handler(commands=['broadcast'])
def broadcast_cmd(message):
    if not is_admin(message.from_user.id): return
    text_to_send = message.text.replace("/broadcast", "").strip()
    if not text_to_send:
        user_states[message.from_user.id] = "WAITING_BROADCAST_TEXT"
        bot.reply_to(message, "📢 **Send the text message you want to broadcast:**", parse_mode="Markdown")
        return
    
    cursor.execute("SELECT user_id FROM users WHERE banned = 0")
    users = cursor.fetchall()
    s, f = 0, 0
    for u in users:
        try:
            bot.send_message(u[0], text_to_send, parse_mode="Markdown")
            s += 1
        except:
            f += 1
    bot.reply_to(message, f"📢 **Broadcast Sent!**\n✅ Success: `{s}` | ❌ Failed: `{f}`", parse_mode="Markdown")

@bot.message_handler(commands=['broadcastphoto'])
def broadcast_photo_cmd(message):
    if not is_admin(message.from_user.id): return
    user_states[message.from_user.id] = "WAITING_BROADCAST_PHOTO"
    bot.reply_to(message, "🖼️ **Please upload the photo you want to broadcast:**", parse_mode="Markdown")

@bot.message_handler(commands=['uploadqr'])
def upload_qr_cmd(message):
    if not is_admin(message.from_user.id): return
    user_states[message.from_user.id] = "WAITING_QR_PHOTO"
    bot.reply_to(message, "📩 **Please upload the QR Code image:**", parse_mode="Markdown")

@bot.message_handler(commands=['newqr'])
def new_qr_cmd(message):
    upload_qr_cmd(message)

@bot.message_handler(commands=['addbalance'])
def add_balance_cmd(message):
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Usage: `/addbalance <user_id> <amount>`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[1])
        amount = float(args[2])
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, target_id))
        conn.commit()
        bot.reply_to(message, f"➕ **Added ₹{amount:.2f} to user `{target_id}`.**", parse_mode="Markdown")
        try:
            bot.send_message(target_id, f"🎉 **Admin added ₹{amount:.2f} to your balance!**", parse_mode="Markdown")
        except:
            pass
    except ValueError:
        bot.reply_to(message, "❌ Invalid inputs!")

@bot.message_handler(commands=['deductbalance'])
def deduct_balance_cmd(message):
    if not is_admin(message.from_user.id): return
    args = message.text.split()
    if len(args) < 3:
        bot.reply_to(message, "⚠️ Usage: `/deductbalance <user_id> <amount>`", parse_mode="Markdown")
        return
    try:
        target_id = int(args[1])
        amount = float(args[2])
        cursor.execute("UPDATE users SET balance = MAX(0, balance - ?) WHERE user_id = ?", (amount, target_id))
        conn.commit()
        bot.reply_to(message, f"➖ **Deducted ₹{amount:.2f} from user `{target_id}`.**", parse_mode="Markdown")
        try:
            bot.send_message(target_id, f"⚠️ **Admin deducted ₹{amount:.2f} from your balance.**", parse_mode="Markdown")
        except:
            pass
    except ValueError:
        bot.reply_to(message, "❌ Invalid inputs!")

# ---------------------------------------------------------
# 5. FIXED APPROVAL REQUEST WORKFLOW (EXACT SCREENSHOT UI)
# ---------------------------------------------------------
@bot.callback_query_handler(func=lambda call: call.data.startswith("claim_qr_"))
def claim_qr_handler(call):
    uid = call.from_user.id
    if is_banned(uid):
        bot.answer_callback_query(call.id, "❌ You are banned!", show_alert=True)
        return

    task_id = int(call.data.replace("claim_qr_", ""))
    
    cursor.execute("SELECT qr_file_id, status FROM qr_tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    
    if not row:
        bot.answer_callback_query(call.id, "❌ Task not found!", show_alert=True)
        return
        
    qr_file_id, status = row
    
    if status != 'AVAILABLE':
        bot.answer_callback_query(call.id, "⚠️ This QR has already been claimed or expired!", show_alert=True)
        return

    # LOCK USER STATE FOR PROOF SUBMISSION
    user_states[uid] = f"WAITING_PROOF_{task_id}"
    bot.answer_callback_query(call.id, "✅ QR Unlocked!")

    caption = (
        "💳 **Authorise payment with your app**\n\n"
        "Scan this QR code using your preferred UPI app and follow instructions to pay.\n\n"
        "📸 **Important:** After completing payment, send the **Screenshot (Proof)** here for Admin Approval!"
    )
    bot.send_photo(call.message.chat.id, qr_file_id, caption=caption, parse_mode="Markdown")

# Admin Uploading QR OR User Submitting Payment Proof
@bot.message_handler(content_types=['photo'])
def handle_photos(message):
    uid = message.from_user.id
    register_user(uid, message.from_user.username)
    state = str(user_states.get(uid, ""))

    # 1. Admin Uploading QR Code (Broadcasts EXACT SCREENSHOT UI)
    if is_admin(uid) and state == "WAITING_QR_PHOTO":
        file_id = message.photo[-1].file_id
        cursor.execute("INSERT INTO qr_tasks (qr_file_id, price, status) VALUES (?, ?, 'AVAILABLE')", (file_id, 8.0))
        conn.commit()
        task_id = cursor.lastrowid
        user_states[uid] = None
        
        bot.reply_to(message, f"✅ **New QR Task #{task_id} saved! Broadcasting...**", parse_mode="Markdown")
        
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton("💳 Make Payment", callback_data=f"claim_qr_{task_id}")
        markup.add(btn)
        
        text_broadcast = (
            "📢 **NEW QR AVAILABLE**\n\n"
            "Tap 💳 **Make Payment** to claim the QR.\n"
            "Only the first eligible member can claim it."
        )
        
        cursor.execute("SELECT user_id FROM users WHERE banned = 0")
        users = cursor.fetchall()
        s = 0
        for u in users:
            try:
                bot.send_message(u[0], text_broadcast, reply_markup=markup, parse_mode="Markdown")
                s += 1
            except:
                pass
        bot.send_message(message.chat.id, f"🚀 **Broadcasted to `{s}` users!**", parse_mode="Markdown")
        return

    # 2. Admin Broadcast Photo
    if is_admin(uid) and state == "WAITING_BROADCAST_PHOTO":
        user_states[uid] = None
        photo_id = message.photo[-1].file_id
        caption = message.caption or ""
        
        cursor.execute("SELECT user_id FROM users WHERE banned = 0")
        users = cursor.fetchall()
        s, f = 0, 0
        for u in users:
            try:
                bot.send_photo(u[0], photo_id, caption=caption, parse_mode="Markdown")
                s += 1
            except:
                f += 1
        bot.reply_to(message, f"🖼️ **Photo Broadcast Sent!**\n✅ Success: `{s}` | ❌ Failed: `{f}`", parse_mode="Markdown")
        return

    # 3. User Submitting Payment Screenshot Proof (100% FIXED REQUEST TO ADMIN)
    if state.startswith("WAITING_PROOF_") or not is_admin(uid):
        task_id = 0
        if state.startswith("WAITING_PROOF_"):
            try:
                task_id = int(state.replace("WAITING_PROOF_", ""))
            except:
                task_id = 0
        
        proof_file_id = message.photo[-1].file_id

        cursor.execute("INSERT INTO submissions (task_id, user_id, proof_file_id, status) VALUES (?, ?, ?, 'PENDING')",
                       (task_id, uid, proof_file_id))
        conn.commit()
        sub_id = cursor.lastrowid
        user_states[uid] = None

        bot.reply_to(
            message,
            "⏳ **APPROVAL REQUEST SUBMITTED!** ⏳\n\n"
            "Your payment screenshot is being verified by Admin.\n"
            "💰 *₹8.00 will be added to your balance once approved!*",
            parse_mode="Markdown"
        )

        # SEND APPROVAL REQUEST WITH BUTTONS TO ALL ADMINS
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("✅ Approve (₹8)", callback_data=f"appr_{sub_id}"),
            types.InlineKeyboardButton("❌ Reject", callback_data=f"rejc_{sub_id}")
        )
        
        admin_text = (
            "🚨 **NEW TASK APPROVAL REQUEST** 🚨\n\n"
            f"👤 **User ID:** `{uid}` (@{message.from_user.username or 'N/A'})\n"
            f"📌 **Submission ID:** `{sub_id}`\n"
            f"💵 **Reward:** ₹8.00"
        )
        
        cursor.execute("SELECT user_id FROM admins")
        admin_rows = cursor.fetchall()
        admin_list = set(MAIN_ADMINS + [r[0] for r in admin_rows])
        
        for admin_id in admin_list:
            try:
                bot.send_photo(admin_id, proof_file_id, caption=admin_text, reply_markup=markup, parse_mode="Markdown")
            except Exception as e:
                logging.error(f"Error sending approval to admin {admin_id}: {e}")

# Admin Approval / Rejection Action Handler
@bot.callback_query_handler(func=lambda call: call.data.startswith(("appr_", "rejc_")))
def handle_approval_action(call):
    if not is_admin(call.from_user.id): return
    
    action, sub_id = call.data.split("_")
    sub_id = int(sub_id)

    cursor.execute("SELECT task_id, user_id, status FROM submissions WHERE id = ?", (sub_id,))
    row = cursor.fetchone()

    if not row:
        bot.answer_callback_query(call.id, "❌ Submission not found!", show_alert=True)
        return

    task_id, user_id, status = row

    if status != 'PENDING':
        bot.answer_callback_query(call.id, f"⚠️ Already processed ({status})!", show_alert=True)
        return

    if action == "appr":
        cursor.execute("UPDATE submissions SET status = 'APPROVED' WHERE id = ?", (sub_id,))
        cursor.execute("UPDATE users SET balance = balance + 8.0 WHERE user_id = ?", (user_id,))
        conn.commit()

        bot.answer_callback_query(call.id, "✅ Approved successfully!")
        bot.edit_message_caption(call.message.caption + "\n\n✅ **APPROVED BY ADMIN (+₹8.00)**", chat_id=call.message.chat.id, message_id=call.message.message_id)

        try:
            bot.send_message(
                user_id,
                "🎉 **CONGRATULATIONS! YOUR TASK IS APPROVED!** 🎉\n\n"
                "✅ Your payment screenshot was verified.\n"
                "💰 **₹8.00** has been credited to your balance!",
                parse_mode="Markdown"
            )
        except:
            pass

    elif action == "rejc":
        cursor.execute("UPDATE submissions SET status = 'REJECTED' WHERE id = ?", (sub_id,))
        conn.commit()

        bot.answer_callback_query(call.id, "❌ Rejected!")
        bot.edit_message_caption(call.message.caption + "\n\n❌ **REJECTED BY ADMIN**", chat_id=call.message.chat.id, message_id=call.message.message_id)

        try:
            bot.send_message(
                user_id,
                "❌ **TASK REJECTED** ❌\n\n"
                "Your screenshot proof was rejected by Admin. Please submit valid payment proof.",
                parse_mode="Markdown"
            )
        except:
            pass

# ---------------------------------------------------------
# 6. TEXT BUTTON HANDLERS
# ---------------------------------------------------------
@bot.message_handler(func=lambda message: True)
def handle_text(message):
    uid = message.from_user.id
    if is_banned(uid): return
    register_user(uid, message.from_user.username)
    text = message.text.strip()
    state = str(user_states.get(uid, ""))

    # Handle Pending Broadcast Text Input
    if is_admin(uid) and state == "WAITING_BROADCAST_TEXT":
        user_states[uid] = None
        cursor.execute("SELECT user_id FROM users WHERE banned = 0")
        users = cursor.fetchall()
        s, f = 0, 0
        for u in users:
            try:
                bot.send_message(u[0], text, parse_mode="Markdown")
                s += 1
            except:
                f += 1
        bot.reply_to(message, f"📢 **Broadcast Sent!**\n✅ Success: `{s}` | ❌ Failed: `{f}`", parse_mode="Markdown")
        return

    # User Reply Keyboard Buttons
    if "Get QR" in text:
        cursor.execute("SELECT id, qr_file_id FROM qr_tasks WHERE status = 'AVAILABLE' ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        if not row:
            bot.send_message(message.chat.id, "There is no QR available right now.\nPlease wait for the next task update!", parse_mode="Markdown")
            return

        task_id, qr_file_id = row
        markup = types.InlineKeyboardMarkup()
        btn = types.InlineKeyboardButton("💳 Make Payment", callback_data=f"claim_qr_{task_id}")
        markup.add(btn)

        caption_text = (
            "📢 **NEW QR AVAILABLE**\n\n"
            "Tap 💳 **Make Payment** to claim the QR.\n"
            "Only the first eligible member can claim it."
        )
        bot.send_message(message.chat.id, caption_text, reply_markup=markup, parse_mode="Markdown")

    elif "Balance" in text:
        balance_cmd(message)

    elif "Withdrawal" in text:
        withdrawal_cmd(message)

    elif "History" in text:
        cursor.execute("SELECT COUNT(*) FROM submissions WHERE user_id = ? AND status = 'APPROVED'", (uid,))
        appr = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM submissions WHERE user_id = ? AND status = 'PENDING'", (uid,))
        pend = cursor.fetchone()[0]

        msg = (
            "📜 **YOUR TASK HISTORY** 📜\n\n"
            f"✅ **Approved Tasks:** `{appr}`\n"
            f"⏳ **Pending Approvals:** `{pend}`"
        )
        bot.reply_to(message, msg, parse_mode="Markdown")

    elif "Support" in text:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🆘 Contact Support", url="https://t.me/Dictator_0771"))
        bot.send_message(message.chat.id, "If you need help, contact our support team:", reply_markup=markup, parse_mode="Markdown")

# ---------------------------------------------------------
# 7. MAIN EXECUTION
# ---------------------------------------------------------
if __name__ == "__main__":
    server_thread = threading.Thread(target=run_flask)
    server_thread.daemon = True
    server_thread.start()
    
    ping_thread = threading.Thread(target=self_ping_loop)
    ping_thread.daemon = True
    ping_thread.start()
    
    print("Setting up bot menu commands...")
    setup_bot_menu_commands()

    print("Clearing old session and starting bot...")
    try:
        bot.remove_webhook(drop_pending_updates=True)
        time.sleep(2)
    except Exception as e:
        print(f"Notice: {e}")

    print("Bot polling running in infinite retry loop...")
    while True:
        try:
            bot.infinity_polling(skip_pending=True, timeout=60, long_polling_timeout=60)
        except Exception as e:
            logging.error(f"Polling connection interrupted: {e}. Restarting in 3s...")
            time.sleep(3)
