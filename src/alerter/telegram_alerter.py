import telegram
import asyncio


async def send_telegram_message(bot_token: str, chat_id: str, message: str):
    try:
        bot = telegram.Bot(token=bot_token)
        await bot.send_message(chat_id=chat_id, text=message, parse_mode='HTML') 
        print(f"Telegram message sent to chat ID {chat_id}: \"{message[:50]}...\"")
        return True
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
        return False


def send_telegram_message_sync(bot_token: str, chat_id: str, message: str):
    async def _send():
        return await send_telegram_message(bot_token, chat_id, message)
    
    try:
        return asyncio.run(_send())
    except RuntimeError as e:
        print(f"RuntimeError with asyncio.run: {e}. Consider structuring with a single event loop if using multiple async operations.")
        return False


if __name__ == '__main__':
    import os
    from src.common.config_loader import load_config 


    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    config_path = os.path.join(project_root, 'config.ini')
    
    if os.path.exists(config_path):
        config = load_config(config_path)
        TELEGRAM_BOT_TOKEN = config['TELEGRAM']['BOT_TOKEN']
        TELEGRAM_CHAT_ID = config['TELEGRAM']['CHAT_ID']

        if TELEGRAM_BOT_TOKEN == "YOUR_TELEGRAM_BOT_TOKEN_HERE" or TELEGRAM_CHAT_ID == "YOUR_TELEGRAM_GROUP_CHAT_ID_HERE":
            print("Please update config.ini with your Telegram Bot Token and Chat ID.")
        else:
            print("Attempting to send a test Telegram message (sync wrapper)...")
            success = send_telegram_message_sync(
                TELEGRAM_BOT_TOKEN,
                TELEGRAM_CHAT_ID,
                "Hello from your Price Tracker Bot! This is a test message to affirm that the bot is functioning."
            )
            if success:
                print("Test Telegram message sent successfully (check your Telegram group).")
            else:
                print("Failed to send test Telegram message.")
            
            

    else:
        print(f"Config file not found at {config_path} for direct test.")