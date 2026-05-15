from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from config import BOT_TOKEN
from database import init_db
from handlers import start, button_handler, handle_message, handle_photo, stats, issue_detail


# =========================
# FIX: Clear any leftover sessions on startup
# This prevents "Conflict: terminated by other getUpdates request"
# which happens when Railway runs multiple instances during redeploy.
# =========================

async def post_init(application):
    await application.bot.delete_webhook(drop_pending_updates=True)
    print("[BOT] Webhook cleared. Starting fresh polling session.")


# =========================
# BUILD APP
# =========================

app = (
    ApplicationBuilder()
    .token(BOT_TOKEN)
    .post_init(post_init)
    .build()
)


# =========================
# HANDLERS
# =========================

# User commands
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("Start", start))
app.add_handler(CommandHandler("starts", start))
app.add_handler(CommandHandler("Starts", start))
app.add_handler(CommandHandler("aliadmin", stats))
app.add_handler(CommandHandler("issue", issue_detail))

# Buttons and messages
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))


# =========================
# MAIN
# =========================

def main():
    init_db()
    print("[BOT] Database initialized.")
    print("[BOT] Bot is running...")
    app.run_polling(
        allowed_updates=["message", "callback_query"],
        drop_pending_updates=True,   # ignore any messages sent while bot was offline
    )

if __name__ == "__main__":
    main()