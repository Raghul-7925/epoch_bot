import time
import json
import os
import asyncio
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

# ================= CONFIG =================

BOT_TOKEN = os.environ["BOT_TOKEN"]
OWNER_ID = 1837260280   # only allowed in groups
AUTO_DELETE_SECONDS = 320

DATA_FILE = "data.json"

EPOCH_SECONDS = 330
TOTAL_EPOCHS = 288
TAPS_PER_EPOCH = 70
MAX_TAPS = 12000

# =========================================


# ---------------- Permission Check ----------------

async def is_allowed(update: Update):
    chat = update.effective_chat
    user = update.effective_user

    if chat.type == "private":
        return True

    return user.id == OWNER_ID


# ---------------- Auto Delete ----------------

async def auto_delete(context, chat_id, message_id, delay=AUTO_DELETE_SECONDS):
    await asyncio.sleep(delay)
    try:
        await context.bot.delete_message(chat_id, message_id)
    except:
        pass


async def send_reply(update, context, text, reply_markup=None):
    msg = await update.effective_chat.send_message(
        text=text,
        reply_markup=reply_markup
    )
    if update.effective_chat.type != "private":
        context.application.create_task(
            auto_delete(context, msg.chat_id, msg.message_id)
        )
    return msg


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
    if not await is_allowed(update):
        return

    await send_reply(
        update,
        context,
        "⏱️ AckiNacki Epoch Timer – Intro\n\n"
        "After your first Popit tap of the day, send /on to start your personal "
        "330 second epochs.\n\n"
        "Each epoch is based on 70 taps. For best accuracy, complete exactly "
        "70 taps within one epoch."
    )


async def on(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update):
        return

    data = load_data()
    uid = str(update.effective_user.id)
    chat_id = update.effective_chat.id
    now = int(time.time())

    job_name = f"epoch_{chat_id}"

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
        "chat_id": chat_id,
        "job_name": job_name
    }

    save_data(data)

    context.job_queue.run_repeating(
        callback=epoch_job,
        interval=EPOCH_SECONDS,
        first=EPOCH_SECONDS,
        name=job_name,
        data={"uid": uid}
    )

    # ✅ IMPORTANT FIX: show Epoch 1 using same status logic
    await send_status(context, update.effective_user.id, force=True)


async def off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update):
        return

    data = load_data()
    uid = str(update.effective_user.id)

    if uid in data:
        data[uid]["notify"] = False
        save_data(data)

    await send_reply(update, context, "🔕 Notifications OFF. Epoch timing continues.")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update):
        return

    data = load_data()
    uid = str(update.effective_user.id)

    if uid in data:
        job_name = data[uid]["job_name"]
        for job in context.job_queue.jobs():
            if job.name == job_name:
                job.schedule_removal()

        del data[uid]
        save_data(data)

    await send_reply(update, context, "♻️ Reset complete. Tracking stopped.")


# ---------------- TAP CORE ----------------

async def tap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update):
        return

    data = load_data()
    uid = str(update.effective_user.id)

    if uid not in data:
        await send_reply(update, context, "Use /on first.")
        return

    if not context.args:
        await send_reply(update, context, "Use /tap add or /tap remove")
        return

    action = context.args[0].lower()

    if action == "add":
        data[uid]["tapped_epochs"] += 1
        save_data(data)
        await send_reply(update, context, "✅ One tapped epoch added.")

    elif action == "remove":
        if data[uid]["tapped_epochs"] > 0:
            data[uid]["tapped_epochs"] -= 1
            save_data(data)
            await send_reply(update, context, "➖ One tapped epoch removed.")
        else:
            await send_reply(update, context, "Tapped epochs already zero.")


async def tapadd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args = ["add"]
    await tap(update, context)


async def tapremove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.args = ["remove"]
    await tap(update, context)


async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_allowed(update):
        return

    await send_status(context, update.effective_user.id, force=True)


# ---------------- Epoch Logic ----------------

async def send_status(context, user_id, force=False):
    data = load_data()
    uid = str(user_id)

    if uid not in data or not data[uid]["active"]:
        return

    now = int(time.time())
    elapsed = now - data[uid]["cycle_start"]

    epoch = elapsed // EPOCH_SECONDS + 1
    if epoch > TOTAL_EPOCHS:
        epoch = TOTAL_EPOCHS

    if not force and epoch == data[uid]["last_epoch_sent"]:
        return

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
        f"⏱️ Epoch {epoch} / {TOTAL_EPOCHS}\n"
        f"⌛ Remaining: {remaining_cycle} epochs\n\n"
        f"✅ Tapped Epochs: {tapped}\n"
        f"🏆 Reward Tier: {tier}\n\n"
        f"🟢 Used Taps: {used_taps}\n"
        f"🔵 Remaining Taps: {remaining_taps} / {MAX_TAPS}"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ Tapped", callback_data="tapped"),
            InlineKeyboardButton("⏭️ Not Tapped", callback_data="skipped"),
        ]
    ])

    msg = await context.bot.send_message(
        chat_id=data[uid]["chat_id"],
        text=text,
        reply_markup=keyboard
    )

    if msg.chat.type != "private":
        context.application.create_task(
            auto_delete(context, msg.chat_id, msg.message_id)
        )


async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    uid = str(query.from_user.id)
    data = load_data()

    if uid not in data:
        return

    data[uid]["current_decision"] = (
        "tapped" if query.data == "tapped" else "skipped"
    )
    save_data(data)

    await query.edit_message_reply_markup(None)


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
app.add_handler(CommandHandler("tapadd", tapadd))
app.add_handler(CommandHandler("tapremove", tapremove))

app.add_handler(CallbackQueryHandler(button_handler))

app.run_polling()
