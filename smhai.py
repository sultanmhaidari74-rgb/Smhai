
import os
import logging
import asyncio
import time

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)
from google import genai
from google.genai import types


# Load environment variables
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")


# Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# Check configuration
if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError("Missing Telegram or Gemini API key.")

if not WEBHOOK_SECRET or not RENDER_URL:
    raise ValueError("Missing webhook configuration.")


# Gemini client
client = genai.Client(api_key=GEMINI_API_KEY)

# Conversation memory
user_memory = {}


SYSTEM_PROMPT = """
You are Sultan AI, an intelligent and helpful assistant.

Understand the user's language and respond in the same language.

Be friendly, accurate, professional, and respectful.

If the user writes in Dari or Persian,
respond in natural Dari/Persian.

If the user writes in English,
respond in clear and natural English.

Give accurate, useful, and well-structured answers.

Never reveal API keys, tokens, or private configuration.
"""


# Start command
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "سلام! 👋\n"
        "من Sultan AI هستم، دستیار هوشمند شما "
        "با قدرت Google Gemini.\n\n"
        "پیام خود را بفرستید تا گفتگو را شروع کنیم. 🤖"
    )


# Help command
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    await update.message.reply_text(
        "دستورات Sultan AI:\n\n"
        "/start - شروع ربات\n"
        "/help - راهنما\n"
        "/reset - پاک کردن حافظه گفتگو"
    )


# Reset conversation
async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id

    user_memory.pop(user_id, None)

    await update.message.reply_text(
        "حافظه گفتگوی شما پاک شد. 🧹"
    )


# Main AI chat
async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user_id = update.effective_user.id
    user_text = update.message.text

    try:

        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action="typing",
        )

        # Copy conversation history
        history = list(user_memory.get(user_id, []))

        history.append(
            types.Content(
                role="user",
                parts=[
                    types.Part.from_text(text=user_text)
                ],
            )
        )

        start_time = time.monotonic()

        logger.info(
            "Gemini request started. Model: %s",
            GEMINI_MODEL,
        )

        # Send request to Gemini
        response = await asyncio.wait_for(

            client.aio.models.generate_content(

                model=GEMINI_MODEL,

                contents=history,

                config=types.GenerateContentConfig(

                    system_instruction=SYSTEM_PROMPT,

                    thinking_config=types.ThinkingConfig(
                        thinking_level="low"
                    ),

                    max_output_tokens=2048,

                ),

            ),

            timeout=90,

        )

        answer = response.text

        if not answer:
            answer = "متأسفانه پاسخی دریافت نکردم. لطفاً دوباره تلاش کنید."

        elapsed = time.monotonic() - start_time

        logger.info(
            "Gemini response received in %.2f seconds",
            elapsed,
        )

        # Save conversation
        history.append(
            types.Content(
                role="model",
                parts=[
                    types.Part.from_text(text=answer)
                ],
            )
        )

        user_memory[user_id] = history[-20:]

        # Send response to Telegram
        for i in range(0, len(answer), 4000):

            await update.message.reply_text(
                answer[i:i + 4000]
            )

    except asyncio.TimeoutError:

        logger.error(
            "Gemini request timed out after 90 seconds."
        )

        await update.message.reply_text(
            "پاسخ هوش مصنوعی بیش از حد طول کشید. "
            "لطفاً دوباره تلاش کنید. ⏳"
        )

    except Exception:

        logger.exception(
            "Gemini request failed."
        )

        await update.message.reply_text(
            "در ارتباط با هوش مصنوعی مشکلی رخ داد. "
            "لطفاً دوباره تلاش کنید."
        )


# Main application
def main():

    app = Application.builder().token(
        TELEGRAM_TOKEN
    ).build()

    # Commands
    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("help", help_command)
    )

    app.add_handler(
        CommandHandler("reset", reset_command)
    )

    # Text messages
    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            chat,
        )
    )

    port = int(
        os.environ.get("PORT", "10000")
    )

    logger.info("Starting Sultan AI webhook server...")

    app.run_webhook(

        listen="0.0.0.0",

        port=port,

        url_path="telegram",

        webhook_url=(
            f"{RENDER_URL.rstrip('/')}/telegram"
        ),

        secret_token=WEBHOOK_SECRET,

    )


if __name__ == "__main__":
    main()
    
