import logging
import os
import asyncio
import asyncpg
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

# Загрузка токена и адреса базы из переменных окружения
API_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и планировщика
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
scheduler = AsyncIOScheduler()

# Подключение к базе данных
async def create_tables():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            chat_id BIGINT,
            task TEXT
        )
    """)
    await conn.close()

async def add_task(chat_id, task):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("INSERT INTO tasks (chat_id, task) VALUES ($1, $2)", chat_id, task)
    await conn.close()

async def get_tasks(chat_id):
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT task FROM tasks WHERE chat_id = $1", chat_id)
    await conn.close()
    return [r['task'] for r in rows]

async def delete_task(chat_id, task):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("DELETE FROM tasks WHERE chat_id = $1 AND task = $2", chat_id, task)
    await conn.close()

# Команда /start
@dp.message_handler(commands=["start"])
async def send_welcome(message: types.Message):
    chat_id = message.chat.id
    await add_task(chat_id, "Полити каву")
    await add_task(chat_id, "Помий барну стійку")
    await message.answer("👋 Привіт! Я бот задач для персоналу ресторану GRECO.")
    scheduler.add_job(send_weekly_tasks, CronTrigger(day_of_week='mon', hour=11, minute=30), args=[chat_id])
    await message.answer("📅 Щопонеділка о 11:30 я буду надсилати задачі для бару та залу.")

# Команда /task
@dp.message_handler(commands=["task"])
async def list_tasks(message: types.Message):
    user_tasks = await get_tasks(message.chat.id)
    if not user_tasks:
        await message.answer("✅ У тебе немає активних задач!")
        return
    buttons = [InlineKeyboardButton(text=f"✅ {t}", callback_data=f"done:{t}") for t in user_tasks]
    markup = InlineKeyboardMarkup().add(*buttons)
    await message.answer("📝 Список задач:", reply_markup=markup)

# Обработка нажатия на кнопку
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("done:"))
async def mark_done(callback_query: types.CallbackQuery):
    task = callback_query.data.split(":", 1)[1]
    chat_id = callback_query.message.chat.id
    await delete_task(chat_id, task)
    await bot.answer_callback_query(callback_query.id, text=f"Задача виконана: {task}")
    await bot.send_message(chat_id, f"✅ Виконано: {task}")

# Задачи по понедельникам
async def send_weekly_tasks(chat_id):
    await bot.send_message(chat_id, "👨‍🍳 ОФІЦІАНТИ: 🧂 Спецовники заповнені?")
    await bot.send_message(chat_id, "🍸 БАРМЕНИ: 🧼 Фільтри чисті?")

# Подключение планировщика и базы при старте
async def on_startup(dp):
    await create_tables()
    scheduler.start()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
