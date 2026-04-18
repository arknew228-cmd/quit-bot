import os
import random
import html
import requests
import asyncio
from threading import Thread
from flask import Flask
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

# --- Простой веб-сервер для Render (чтобы сервис не засыпал) ---
web_app = Flask(__name__)

@web_app.route('/')
def home():
    return "Бот работает!"

def run_web_server():
    port = int(os.environ.get("PORT", 8443))
    web_app.run(host="0.0.0.0", port=port)

# --- Резервный вопрос на случай проблем с API ---
FALLBACK_QUESTION = {
    "question": "Столица Франции?",
    "options": ["Берлин", "Мадрид", "Париж", "Рим"],
    "answer": 2
}

def fetch_trivia_question():
    """Запрашивает вопрос с OpenTDB на русском языке."""
    try:
        url = "https://opentdb.com/api.php?amount=1&type=multiple&language=ru"
        resp = requests.get(url, timeout=5)
        data = resp.json()
        
        if data.get("response_code") != 0 or not data.get("results"):
            return None
            
        item = data["results"][0]
        question = html.unescape(item["question"])
        correct = html.unescape(item["correct_answer"])
        incorrect = [html.unescape(ans) for ans in item["incorrect_answers"]]
        
        options = incorrect + [correct]
        random.shuffle(options)
        
        return {
            "question": question,
            "options": options,
            "answer": options.index(correct)
        }
    except Exception as e:
        print(f"Ошибка API: {e}")
        return None

def get_question():
    """Возвращает вопрос (из API или резервный)."""
    q = fetch_trivia_question()
    return q if q else FALLBACK_QUESTION.copy()

# Хранилище состояний пользователей (в памяти)
user_state = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🎲 Привет! Я бот-викторина с бесконечными вопросами!\n"
        "/quiz — новый вопрос\n"
        "/score — мой счёт"
    )
    user_state[update.effective_user.id] = {"score": 0, "current_q": None}

async def quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in user_state:
        user_state[user_id] = {"score": 0, "current_q": None}
    
    q_data = get_question()
    user_state[user_id]["current_q"] = q_data
    
    keyboard = [
        [InlineKeyboardButton(opt, callback_data=f"ans_{i}")]
        for i, opt in enumerate(q_data["options"])
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"❓ {q_data['question']}",
        reply_markup=reply_markup
    )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    state = user_state.get(user_id)
    
    if not state or not state.get("current_q"):
        await query.edit_message_text("⏳ Начни с команды /quiz")
        return
    
    q_data = state["current_q"]
    selected = int(query.data.split("_")[1])
    
    if selected == q_data["answer"]:
        state["score"] += 1
        result = f"✅ Правильно! Счёт: {state['score']}"
    else:
        correct = q_data["options"][q_data["answer"]]
        result = f"❌ Неверно. Правильно: {correct}\nСчёт: {state['score']}"
    
    keyboard = [[InlineKeyboardButton("➡️ Следующий вопрос", callback_data="next_q")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(result, reply_markup=reply_markup)
    state["current_q"] = None

async def next_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    q_data = get_question()
    user_state[user_id]["current_q"] = q_data
    
    keyboard = [
        [InlineKeyboardButton(opt, callback_data=f"ans_{i}")]
        for i, opt in enumerate(q_data["options"])
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await query.edit_message_text(
        f"❓ {q_data['question']}",
        reply_markup=reply_markup
    )

async def score(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    state = user_state.get(user_id, {})
    s = state.get("score", 0)
    await update.message.reply_text(f"🏆 Твой счёт: {s}")

def main():
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise ValueError("Не задан BOT_TOKEN")
    
    app = Application.builder().token(token).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("quiz", quiz))
    app.add_handler(CommandHandler("score", score))
    app.add_handler(CallbackQueryHandler(button_handler, pattern="^ans_"))
    app.add_handler(CallbackQueryHandler(next_question, pattern="^next_q$"))
    
    # Запускаем веб-сервер в отдельном потоке (для Render)
    Thread(target=run_web_server).start()
    
    # Запускаем бота в режиме polling (он сам будет спрашивать Telegram)
    app.run_polling()

if __name__ == "__main__":
    main()
