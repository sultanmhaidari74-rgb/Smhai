
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
    BusinessConnectionHandler,
    filters,
)

from google import genai
from google.genai import types


# ==========================================
# 1. ENVIRONMENT VARIABLES
# ==========================================

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")

WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")
RENDER_URL = os.getenv("RENDER_EXTERNAL_URL")

PORT = int(os.getenv("PORT", "10000"))


# ==========================================
# 2. LOGGING
# ==========================================

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger(__name__)


# ==========================================
# 3. CHECK CONFIGURATION
# ==========================================

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is missing")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing")

if not WEBHOOK_SECRET:
    raise ValueError("TELEGRAM_WEBHOOK_SECRET is missing")

if not RENDER_URL:
    raise ValueError("RENDER_EXTERNAL_URL is missing")


# ==========================================
# 4. GEMINI CLIENT
# ==========================================

client = genai.Client(api_key=GEMINI_API_KEY)

SYSTEM_PROMPT = """
You are Sultan AI, a helpful, intelligent and friendly AI assistant.

Your responsibilities:
- Answer questions clearly and accurately.
- Understand English, Dari, Persian and other languages.
- Reply in the same language used by the user.
- Help with education, programming, research, GIS, urban planning,
  data science and everyday questions.
- Explain difficult topics in simple language when needed.
- Never invent facts when you are uncertain.
- Be respectful, professional and concise.
"""


# ==========================================
# 5. CONVERSATION MEMORY
# ==========================================

# Memory is separated by chat and user.
# Business chats also use their business connection ID.
user_memory = {}

MAX_HISTORY_MESSAGES = 12


def get_memory_key(update, business_connection_id=None):
    user = update.effective_user
    chat = update.effective_chat

    if not user or not chat:
        return None

    return (
        business_connection_id,
        chat.id,
        user.id,
    )


# ==========================================
# 6. START COMMAND
# ==========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    message = update.effective_message

    if message:
        await message.reply_text(
            "سلام! 👋\n\n"
            "من سلطان AI هستم.\n"
            "هر سوالی داری بپرس؛ آماده‌ام کمکت کنم."
        )


# ==========================================
# 7. HELP COMMAND
# ==========================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    message = update.effective_message

    if message:
        await message.reply_text(
            "راهنمای سلطان AI 🤖\n\n"
            "/start - شروع ربات\n"
            "/help - راهنما\n"
            "/reset - پاک کردن حافظه گفت‌وگو\n\n"
            "همچنین می‌توانی مستقیماً سوالت را بنویسی."
        )


# ==========================================
# 8. RESET MEMORY
# ==========================================

async def reset_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    message = update.effective_message

    if not message:
        return

    business_id = (
        message.business_connection_id
        if message.business_connection_id
        else None
    )

    memory_key = get_memory_key(update, business_id)

    if memory_key:
        user_memory.pop(memory_key, None)

    await message.reply_text(
        "حافظه این گفت‌وگو پاک شد. ✅"
    )


# ==========================================
# 9. BUSINESS CONNECTION HANDLER
# ==========================================

async def business_connection_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    connection = update.business_connection

    if not connection:
        return

    logger.info(
        "Business connection update received. Enabled: %s",
        connection.is_enabled,
    )


# ==========================================
# 10. MAIN AI CHAT HANDLER
# ==========================================

async def chat(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
):

    message = update.effective_message
    user = update.effective_user
    chat_info = update.effective_chat

    if not message or not user or not chat_info:
        return

    # Ignore messages without text
    if not message.text:
        return

    # Ignore commands
    if message.text.startswith("/"):
        return

    business_id = message.business_connection_id

    # --------------------------------------
    # Check Telegram Business connection
    # --------------------------------------

    if business_id:

        try:
            connection = await context.bot.get_business_connection(
                business_connection_id=business_id
            )

            # Ignore messages sent by the business account owner
            if user.id == connection.user.id:
                return

            # Ignore disabled connections
            if not connection.is_enabled:
                logger.warning("Business connection is disabled")
                return

        except Exception:
            logger.exception("Could not verify business connection")
            return

    memory_key = get_memory_key(update, business_id)

    if memory_key is None:
        return

    # --------------------------------------
    # Show typing for normal bot chats
    # --------------------------------------

    if not business_id:

        try:
            await context.bot.send_chat_action(
                chat_id=chat_info.id,
                action="typing",
            )
        except Exception:
            logger.warning("Could not send typing action")

    # --------------------------------------
    # Prepare conversation history
    # --------------------------------------

    history = list(user_memory.get(memory_key, []))

    history.append(
        types.Content(
            role="user",
            parts=[
                types.Part.from_text(text=message.text)
            ],
        )
    )

    # --------------------------------------
    # Request Gemini response
    # --------------------------------------

    try:

        logger.info(
            "Gemini request started. Model: %s",
            GEMINI_MODEL,
        )

        start_time = time.monotonic()

        response = await asyncio.wait_for(
            client.aio.models.generate_content(
                model=GEMINI_MODEL,
                contents=history,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    thinking_config=types.ThinkingConfig(
                        thinking_level="low"
                    ),
                ),
            ),
            timeout=90,
        )

        answer = response.text

        if not answer:
            answer = "متأسفم، نتوانستم پاسخ مناسبی تولید کنم. لطفاً دوباره امتحان کن."

        elapsed = round(time.monotonic() - start_time, 2)

        logger.info(
            "Gemini response received in %s seconds",
            elapsed,
        )

        # ----------------------------------
        # Save conversation history
        # ----------------------------------

        history.append(
            types.Content(
                role="model",
                parts=[
                    types.Part.from_text(text=answer)
                ],
            )
        )

        user_memory[memory_key] = history[-MAX_HISTORY_MESSAGES:]

        # ----------------------------------
        # Send answer to Telegram
        # ----------------------------------

        for i in range(0, len(answer), 4000):

            part = answer[i:i + 4000]

            if business_id:

                # Reply inside the connected Business chat
                await context.bot.send_message(
                    chat_id=chat_info.id,
                    text=part,
                    business_connection_id=business_id,
                )

            else:

                # Normal bot conversation
                await message.reply_text(part)

    except asyncio.TimeoutError:

        logger.error("Gemini request timed out after 90 seconds")

        error_text = (
            "پاسخ هوش مصنوعی کمی طول کشید. "
            "لطفاً دوباره پیام بده. ⏳"
        )

        if business_id:
            await context.bot.send_message(
                chat_id=chat_info.id,
                text=error_text,
                business_connection_id=business_id,
            )
        else:
            await message.reply_text(error_text)

    except Exception:

        logger.exception("AI chat handler failed")

        error_text = (
            "در پردازش پیام مشکلی پیش آمد. "
            "لطفاً چند لحظه بعد دوباره تلاش کن."
        )

        try:

            if business_id:
                await context.bot.send_message(
                    chat_id=chat_info.id,
                    text=error_text,
                    business_connection_id=business_id,
                )
            else:
                await message.reply_text(error_text)

        except Exception:
            logger.exception("Could not send error message")


# ==========================================
# 11. MAIN APPLICATION
# ==========================================

def main():

    logger.info("Starting Sultan AI...")

    app = (
        Application.builder()
        .token(TELEGRAM_TOKEN)
        .build()
    )

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

    # Telegram Business connection updates
    app.add_handler(
        BusinessConnectionHandler(
            business_connection_handler
        )
    )

    # Normal private bot messages
    app.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE
            & filters.TEXT
            & ~filters.COMMAND,
            chat,
        )
    )

    # Telegram Business messages
    app.add_handler(
        MessageHandler(
            filters.UpdateType.BUSINESS_MESSAGE
            & filters.TEXT
            & ~filters.COMMAND,
            chat,
        )
    )

    logger.info("Handlers registered successfully")

    # Start Telegram webhook
    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="telegram",
        webhook_url=f"{RENDER_URL.rstrip('/')}/telegram",
        secret_token=WEBHOOK_SECRET,
        allowed_updates=[
            "message",
            "business_message",
            "business_connection",
        ],
    )


# ==========================================
# 12. RUN
# ==========================================

if __name__ == "__main__":
    main()
    
