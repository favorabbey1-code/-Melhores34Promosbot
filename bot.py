import os
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters
# ... (keep all your existing handlers, keyboards, and config)

def main():
    # Railway injects PORT and RAILWAY_PUBLIC_DOMAIN
    PORT = int(os.getenv("PORT", 8080))
    RAILWAY_DOMAIN = os.getenv("RAILWAY_PUBLIC_DOMAIN")
    WEBHOOK_URL = f"https://{RAILWAY_DOMAIN}/webhook"

    app = Application.builder().token(BOT_TOKEN).build()

    # Add your handlers (same as before)
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("settings", cmd_settings))
    app.add_handler(CommandHandler("cancel", cmd_cancel))
    app.add_handler(MessageHandler(
        filters.VIDEO | filters.Document.VIDEO | filters.ANIMATION, on_video
    ))
    app.add_handler(CallbackQueryHandler(on_callback))

    print(f"Starting webhook on port {PORT}")
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=WEBHOOK_URL,
        close_loop=False,  # Prevents "Event loop is closed" crash
        allowed_updates=Update.ALL_TYPES
    )

if __name__ == "__main__":
    main()
