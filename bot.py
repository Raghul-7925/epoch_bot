import time
import json
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

DATA_FILE = "data.json"
EPOCH_SECONDS = 300
TOTAL_EPOCHS = 288


def load_data():
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except:
        return {}


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = {
        "start_time": int(time.time()),
        "chat_id": update.effective_chat.id,
        "last_epoch": 0
    }
    save_data(data)
    await update.message.reply_text("Timer started. Epoch 1 in progress.")


async def time_now(update: Update, context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if "start_time" not in data:
        await update.message.reply_text("Timer not started.")
        return

    now = int(time.time())
    elapsed = now - data["start_time"]
    epoch = elapsed // EPOCH_SECONDS + 1
    remaining = EPOCH_SECONDS - (elapsed % EPOCH_SECONDS)

    await update.message.reply_text(
        f"Epoch: {epoch}/{TOTAL_EPOCHS}\n"
        f"Remaining in current epoch: {remaining} seconds"
    )


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    save_data({})
    await update.message.reply_text("Timer reset. Send /start to begin again.")


async def epoch_checker(context: ContextTypes.DEFAULT_TYPE):
    data = load_data()
    if "start_time" not in data:
        return

    now = int(time.time())
    elapsed = now - data["start_time"]
    finished_epoch = elapsed // EPOCH_SECONDS

    if finished_epoch > data.get("last_epoch", 0) and finished_epoch <= TOTAL_EPOCHS:
        next_epoch = finished_epoch + 1

        if next_epoch <= TOTAL_EPOCHS:
            message = (
                f"Epoch {finished_epoch} Completed ⏹️\n"
                f"Epoch {next_epoch} In Progress. Tap to participate 👇"
            )
        else:
            message = f"Epoch {finished_epoch} Completed ⏹️\nAll epochs completed."

        await context.bot.send_message(
            chat_id=data["chat_id"],
            text=message
        )

        data["last_epoch"] = finished_epoch
        save_data(data)


app = ApplicationBuilder().token(os.environ["BOT_TOKEN"]).build()

app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("time", time_now))
app.add_handler(CommandHandler("reset", reset))

app.job_queue.run_repeating(epoch_checker, interval=10, first=10)

app.run_polling()
