def main():
    PORT = int(os.getenv("PORT", 8080))
    app = Application.builder().token(BOT_TOKEN).build()
    
    # ... your handlers ...
    
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="webhook",
        webhook_url=f"https://{os.getenv('RAILWAY_PUBLIC_DOMAIN')}/webhook"
    )
