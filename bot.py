import time
import json
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

# ================= CONFIG =================

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = 1837260280
AUTO_DELETE_SECONDS = 320

DATA_FILE = "data.json"

EPOCH_SECONDS = 330
TOTAL_EPOCHS = 288
TAPS_PER_EPOCH = 70
MAX_TAPS = 12000

# =========================================


# ---------------- Permissions ----------------

async def is_allowed(update: Update):
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        return True
    return user.id == OWNER_ID


# ---------------- Storage ----------------

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


# ---------------- Auto Delete ----------------

async def auto_delete(context, chat_id, message_id):
    await asyncio.sleep(AUTO_DELETE_SECONDS)
    try:
        await context.bot.delete_message(chat_id, message_id)
    except:
        pass


# ---------------- Reward Tier ----------------

def get_reward_tier(tapped):
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
        if a <= tapped <= b:
            return a, b, name
    return None, None, "Inefficient"


# ---------------- Commands ----------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update):
        return
    await update.effective_chat.send_message(
        "⏱️ AckiNacki Epoch Timer\n\n"
        "After your first Popit tap of the day, send /on.\n"
        "Epoch length: 330 seconds.\n\n"
        "Each epoch assumes 70 taps.\n"
        "Tap exactly 70 times per epoch for best accuracy."
    )


async def on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update):
        return

    data = load_data()
    chat_id = str(update.effective_chat.id)
    now = int(time.time())
    job_name = f"epoch_{chat_id}"

    for job in context.job_queue.jobs():
        if job.name == job_name:
            job.schedule_removal()

    data[chat_id] = {
        "cycle_start": now,
        "last_epoch_sent": 0,
        "tapped_epochs": 0,
        "current_decision": None,
        "notify": True,
        "chat_type": update.effective_chat.type,
        "job_name": job_name,
    }
    save_data(data)

    context.job_queue.run_repeating(
        epoch_job,
        interval=EPOCH_SECONDS,
        first=EPOCH_SECONDS,
        name=job_name,
        data={"chat_id": chat_id},
    )

    await send_status(context, chat_id, force=True)


async def off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update):
        return
    data = load_data()
    chat_id = str(update.effective_chat.id)
    if chat_id in data:
        data[chat_id]["notify"] = False
        save_data(data)
    await update.effective_chat.send_message("🔕 Notifications paused.")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update):
        return
    data = load_data()
    chat_id = str(update.effective_chat.id)
    if chat_id in data:
        job_name = data[chat_id]["job_name"]
        for job in context.job_queue.jobs():
            if job.name == job_name:
                job.schedule_removal()
        del data[chat_id]
        save_data(data)
    await update.effective_chat.send_message("♻️ Reset complete.")


# ---------------- Manual Tap ----------------

async def tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update):
        return
    data = load_data()
    chat_id = str(update.effective_chat.id)
    if chat_id not in data:
        await update.effective_chat.send_message("Use /on first.")
        return
    if not context.args:
        return
    if context.args[0] == "add":
        data[chat_id]["tapped_epochs"] += 1
    elif context.args[0] == "remove" and data[chat_id]["tapped_epochs"] > 0:
        data[chat_id]["tapped_epochs"] -= 1
    save_data(data)


async def tapadd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args = ["add"]
    await tap(update, context)


async def tapremove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args = ["remove"]
    await tap(update, context)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update):
        return
    await send_status(context, str(update.effective_chat.id), force=True)


# ---------------- Epoch Core ----------------

async def send_status(context, chat_id, force=False):
    data = load_data()
    if chat_id not in data:
        return

    entry = data[chat_id]
    now = int(time.time())
    elapsed = now - entry["cycle_start"]

    if elapsed // EPOCH_SECONDS >= TOTAL_EPOCHS:
        if entry["chat_type"] != "private":
            entry.update({
                "cycle_start": now,
                "last_epoch_sent": 0,
                "current_decision": None,
                "tapped_epochs": 0,
            })
            save_data(data)
            elapsed = 0
        else:
            return

    epoch = elapsed // EPOCH_SECONDS + 1
    if not force and epoch == entry["last_epoch_sent"]:
        return

    if entry["current_decision"] == "tapped":
        entry["tapped_epochs"] += 1

    entry["current_decision"] = None
    entry["last_epoch_sent"] = epoch
    save_data(data)

    if not entry["notify"] and not force:
        return

    tapped = entry["tapped_epochs"]
    ts, te, tier = get_reward_tier(tapped)
    remaining_tier = te - tapped if ts else 0
    remaining_cycle = TOTAL_EPOCHS - epoch
    used_taps = tapped * TAPS_PER_EPOCH
    remaining_taps = max(MAX_TAPS - used_taps, 0)

    text = (
        "📊 User 24-Hour Cycle Status\n\n"
        f"⏱️ Epoch {epoch} / {TOTAL_EPOCHS}\n"
        f"⌛ Remaining Epochs in Cycle: {remaining_cycle}\n\n"
        "👤 Tapping Progress\n"
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

    msg = await context.bot.send_message(
        chat_id=int(chat_id),
        text=text,
        reply_markup=keyboard
    )

    if entry["chat_type"] != "private":
        context.application.create_task(
            auto_delete(context, msg.chat_id, msg.message_id)
        )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = load_data()
    chat_id = str(query.message.chat.id)
    if chat_id in data:
        data[chat_id]["current_decision"] = (
            "tapped" if query.data == "tapped" else "skipped"
        )
        save_data(data)
    await query.edit_message_reply_markup(None)


async def epoch_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data["chat_id"]
    await send_status(context, chat_id)


# ---------------- App ----------------

app = ApplicationBuilder().token(BOT_TOKEN).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("on", on))
app.add_handler(CommandHandler("off", off))
app.add_handler(CommandHandler("reset", reset))
app.add_handler(CommandHandler("status", status))

app.add_handler(CommandHandler("tap", tap))
app.add_handler(CommandHandler("tapadd", tapadd))
app.add_handler(CommandHandler("tapremove", tapremove))

app.add_handler(CallbackQueryHandler(button_handler))

app.run_polling()
