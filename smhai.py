import os
import logging

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
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Gemini
if not TELEGRAM_TOKEN or not GEMINI_API_KEY:
    raise ValueError("API keys are missing. Check your .env file.")

client = genai.Client(api_key=GEMINI_API_KEY)

# Temporary conversation memory for each user
user_memory = {}

SYSTEM_PROMPT = """
You are Sultan AI, an intelligent and helpful assistant.
Understand the user's language and respond in the same language.
Be friendly, accurate, and respectful.
If the user writes in Dari or Persian, respond in natural Dari/Persian.
Never reveal API keys or private configuration.
"""

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "سلام! 👋\n"
        "من Sultan AI هستم، دستیار هوشمند شما با قدرت Google Gemini.\n\n"
        "پیام خود را بفرستید تا گفتگو را شروع کنیم. 🤖"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "دستورات Sultan AI:\n\n"
        "/start - شروع ربات\n"
        "/help - راهنما\n"
        "/reset - پاک کردن حافظه گفتگو"
    )

async def reset_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_memory.pop(user_id, None)

    await update.message.reply_text(
        "حافظه گفتگوی شما پاک شد. 🧹"
    )

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_text = update.message.text

await context.bot.send_chat_action(
    chat_id=update.effective_chat.id,
    action="typing"
)
    history = user_memory.get(user_id, [])

    history.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_text)]
        )
    )

    try:
        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=history,
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.7,
                max_output_tokens=2048,
            ),
        )

        answer = response.text or "متأسفانه پاسخی دریافت نکردم."

        history.append(
            types.Content(
                role="model",
                parts=[types.Part.from_text(text=answer)]
            )
        )

        # Keep the latest conversation turns
        user_memory[user_id] = history[-20:]

        for i in range(0, len(answer), 4000):
            await update.message.reply_text(answer[i:i + 4000])

    except Exception:
        logger.exception("Gemini request failed")
        await update.message.reply_text(
            "در ارتباط با هوش مصنوعی مشکلی رخ داد. لطفاً دوباره تلاش کنید."
        )

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("reset", reset_command))

    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, chat)
    )

    print("Sultan AI is running...")
    app.run_polling()

if __name__ == "__main__":
    main()
