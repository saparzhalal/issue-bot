from telegram.ext import ApplicationBuilder, CommandHandler, CallbackQueryHandler, MessageHandler, filters

from config import BOT_TOKEN
from database import init_db
from handlers import start, button_handler, handle_message, handle_photo, stats, issue_detail



# Create Telegram bot app
app = ApplicationBuilder().token(BOT_TOKEN).build()

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

def main():
    init_db()
    print("Bot is running...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()