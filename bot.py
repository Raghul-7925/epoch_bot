import time
import json
import os
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]

DATA_FILE = "data.json"

EPOCH_SECONDS = 300
TOTAL_EPOCHS = 288
TAPS_PER_EPOCH = 70
MAX_TAPS = 12000


# ---------------- Storage ----------------

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ---------------- Reward Tier ----------------

def get_reward_tier(u):
    tiers = [
        (1, 14, "Extremely High"),
        (15, 28, "Very High"),
        (29, 42, "High"),
        (43, 56, "Medium"),
        (57, 70, "Medium–Low"),
        (71, 84, "Inflection Zone"),
        (85, 98, "Low"),
        (99, 112, "Very Low"),
        (113, 126, "Poor"),
        (127, 140, "Near-Waste"),
        (141, 154, "Almost Useless"),
        (155, 168, "Effectively Zero"),
    ]
    for a, b, name in tiers:
        if a <= u <= b:
            return a, b, name
    return None, None, "Inefficient"


# ---------------- Commands ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📘 About This Bot\n\n"
        "• Tracks your personal tapped epochs\n"
        "• Rewards depend only on epochs YOU tap\n"
        "• Skipped epochs do not reduce rewards\n"
        "• 1 epoch = 5 minutes (288 per day)\n\n"
        "Commands:\n"
        "/on – Start or resume notifications\n"
        "/off – Pause notifications only\n"
        "/status – Show current status\n"
        "/tapadd – Manually add a tapped epoch\n"
        "/tapremove – Manually remove a tapped epoch\n"
        "/reset – Reset everything"
    )


async def on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)
    now = int(time.time())

    if uid not in data:
        data[uid] = {
            "cycle_start": now,
            "tapped_epochs": 0,
            "last_epoch_seen": 0,
            "notify": True,
            "active": True,
            "current_decision": None,
            "chat_id": update.effective_chat.id
        }
    else:
        data[uid]["notify"] = True
        data[uid]["active"] = True

    save_data(data)

    await update.message.reply_text("🔔 Notifications ON. Epoch tracking active.")


async def off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)

    if uid in data:
        data[uid]["notify"] = False
        save_data(data)

    await update.message.reply_text("🔕 Notifications OFF. Epoch counting continues.")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)

    if uid in data:
        del data[uid]
        save_data(data)

    await update.message.reply_text("♻️ All data reset. Tracking stopped.")


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_status(context, update.effective_user.id, force=True)


async def tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)

    if uid not in data:
        await update.message.reply_text("Tracking not active. Use /on first.")
        return

    if not context.args:
        await update.message.reply_text("Use /tap add or /tap remove")
        return

    if context.args[0] == "add":
        data[uid]["tapped_epochs"] += 1
        save_data(data)
        await update.message.reply_text("✅ One tapped epoch added.")

    elif context.args[0] == "remove":
        if data[uid]["tapped_epochs"] > 0:
            data[uid]["tapped_epochs"] -= 1
            save_data(data)
            await update.message.reply_text("➖ One tapped epoch removed.")
        else:
            await update.message.reply_text("Tapped epochs already zero.")


# ---------------- Status Logic ----------------

async def send_status(context, user_id, force=False):
    data = load_data()
    uid = str(user_id)

    if uid not in data or not data[uid].get("active"):
        return

    if not data[uid].get("notify") and not force:
        return

    now = int(time.time())
    start = data[uid]["cycle_start"]
    elapsed = now - start

    global_epoch = min(elapsed // EPOCH_SECONDS + 1, TOTAL_EPOCHS)

    if not force and global_epoch == data[uid]["last_epoch_seen"]:
        return

    # finalize previous epoch
    if data[uid]["current_decision"] == "tapped":
        data[uid]["tapped_epochs"] += 1

    data[uid]["current_decision"] = None
    data[uid]["last_epoch_seen"] = global_epoch
    save_data(data)

    remaining_cycle = TOTAL_EPOCHS - global_epoch
    tapped_epochs = data[uid]["tapped_epochs"]

    ts, te, tier = get_reward_tier(tapped_epochs)
    remaining_in_tier = te - tapped_epochs if ts else 0

    used_taps = tapped_epochs * TAPS_PER_EPOCH
    remaining_taps = max(MAX_TAPS - used_taps, 0)

    text = (
        "📊 User 24-Hour Cycle Status\n\n"
        f"⏱️ Cycle Progress: Epoch {global_epoch} / {TOTAL_EPOCHS}\n"
        f"⌛ Remaining in Cycle: {remaining_cycle} epochs\n\n"
        "👤 User Tapping Progress\n"
        f"✅ Tapped Epochs: {tapped_epochs}\n"
        f"🏆 Reward Tier: {tier}\n"
        f"➡️ Remaining Epochs in This Tier: {remaining_in_tier}\n\n"
        "📈 Tap Statistics\n"
        f"🟢 Total Taps Used: {used_taps}\n"
        f"🔵 Remaining Taps: {remaining_taps} / {MAX_TAPS}"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Tapped", callback_data="tapped"),
            InlineKeyboardButton("⏭️ Not Tapped", callback_data="skipped"),
        ]
    ])

    await context.bot.send_message(
        chat_id=data[uid]["chat_id"],
        text=text,
        reply_markup=keyboard
    )


# ---------------- Button Handler ----------------

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = str(query.from_user.id)
    data = load_data()

    if uid not in data:
        return

    if query.data == "tapped":
        data[uid]["current_decision"] = "tapped"
    else:
        data[uid]["current_decision"] = "skipped"

    save_data(data)
    await query.edit_message_reply_markup(None)


# ---------------- Scheduler ----------------

async def epoch_job(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    for uid in data:
        await send_status(context, uid)


# ---------------- App ----------------

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("on", on))
app.add_handler(CommandHandler("off", off))
app.add_handler(CommandHandler("reset", reset))
app.add_handler(CommandHandler("status", status))
app.add_handler(CommandHandler("tap", tap))
app.add_handler(CallbackQueryHandler(button_handler))

app.job_queue.run_repeating(epoch_job, interval=300, first=10)

app.run_polling()
