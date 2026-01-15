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

EPOCH_SECONDS = 330
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
        "⏱️ AckiNacki Epoch Timer – Intro\n\n"
        "Start your day normally. After you tap your first Popit for the new day, "
        "send /on immediately. This sets the start time for your personal 5-minute 30 sec epochs.\n\n"
        "Tap calculations are based on a prediction of 70 taps per epoch. For best accuracy, "
        "complete exactly 70 taps within a single epoch.\n\n"
        "All remaining taps and efficiency shown by the bot are calculated using this "
        "70 taps per epoch model."
    )


async def on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)
    now = int(time.time())

    job_name = f"epoch_{uid}"

    # cancel old job if exists
    for job in context.job_queue.jobs():
        if job.name == job_name:
            job.schedule_removal()

    data[uid] = {
        "cycle_start": now,
        "last_epoch_sent": 0,
        "tapped_epochs": 0,
        "current_decision": None,
        "notify": True,
        "active": True,
        "chat_id": update.effective_chat.id,
        "job_name": job_name
    }

    save_data(data)

    # schedule per-user epoch job (FIRST RUN AFTER 300s)
    context.job_queue.run_repeating(
        callback=epoch_job,
        interval=EPOCH_SECONDS,
        first=EPOCH_SECONDS,
        name=job_name,
        data={"uid": uid}
    )

    await update.message.reply_text(
        "🔔 Notifications ON\n"
        "⏱️ Your personal 330 SEC epoch cycle has started.\n"
        "📩 Epoch 1 Ongoing."
    )


async def off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)

    if uid in data:
        data[uid]["notify"] = False
        save_data(data)

    await update.message.reply_text(
        "🔕 Notifications OFF.\nEpoch timing continues silently."
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)

    if uid in data:
        job_name = data[uid].get("job_name")

        # cancel job
        for job in context.job_queue.jobs():
            if job.name == job_name:
                job.schedule_removal()

        del data[uid]
        save_data(data)

    await update.message.reply_text("♻️ Reset complete. Tracking stopped.")


async def tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    uid = str(update.effective_user.id)

    if uid not in data:
        await update.message.reply_text("Use /on first.")
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


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await send_status(context, update.effective_user.id, force=True)


# ---------------- Core Epoch Logic ----------------

async def send_status(context, user_id, force=False):
    data = load_data()
    uid = str(user_id)

    if uid not in data or not data[uid]["active"]:
        return

    now = int(time.time())
    start = data[uid]["cycle_start"]

    elapsed = now - start
    epoch = elapsed // EPOCH_SECONDS + 1

    if epoch > TOTAL_EPOCHS:
        epoch = TOTAL_EPOCHS

    if not force and epoch == data[uid]["last_epoch_sent"]:
        return

    # finalize previous epoch
    if data[uid]["current_decision"] == "tapped":
        data[uid]["tapped_epochs"] += 1

    data[uid]["current_decision"] = None
    data[uid]["last_epoch_sent"] = epoch
    save_data(data)

    if not data[uid]["notify"] and not force:
        return

    remaining_cycle = TOTAL_EPOCHS - epoch
    tapped = data[uid]["tapped_epochs"]

    ts, te, tier = get_reward_tier(tapped)
    remaining_tier = te - tapped if ts else 0

    used_taps = tapped * TAPS_PER_EPOCH
    remaining_taps = max(MAX_TAPS - used_taps, 0)

    text = (
        "📊 User 24-Hour Cycle Status\n\n"
        f"⏱️ Cycle Progress: Epoch {epoch} / {TOTAL_EPOCHS}\n"
        f"⌛ Remaining in Cycle: {remaining_cycle} epochs\n\n"
        "👤 User Tapping Progress\n"
        f"✅ Tapped Epochs: {tapped}\n"
        f"🏆 Reward Tier: {tier}\n"
        f"➡️ Remaining Epochs in This Tier: {remaining_tier}\n\n"
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


# ---------------- Epoch Job ----------------

async def epoch_job(context: ContextTypes.DEFAULT_TYPE):
    uid = context.job.data["uid"]
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

app.run_polling()
