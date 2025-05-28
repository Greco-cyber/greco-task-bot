import logging
import os
import asyncio
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
import asyncpg

API_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
scheduler = AsyncIOScheduler()

# Установка соединения с базой и создание таблицы
async def create_tables():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT,
            text TEXT
        );
    """)
    await conn.close()

# Добавление задачи
async def add_task(chat_id, text):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("INSERT INTO tasks (chat_id, text) VALUES ($1, $2)", chat_id, text)
    await conn.close()

# Получение задач
async def get_tasks(chat_id):
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT id, text FROM tasks WHERE chat_id = $1", chat_id)
    await conn.close()
    return rows

# Удаление задачи
async def remove_task(task_id):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("DELETE FROM tasks WHERE id = $1", task_id)
    await conn.close()

# Старт
@dp.message_handler(commands=["start"])
async def send_welcome(message: types.Message):
    chat_id = message.chat.id
    await add_task(chat_id, "Полити каву")
    await add_task(chat_id, "Помий барну стійку")
    await message.answer("👋 Привіт! Я бот задач для персоналу ресторану GRECO.")
    scheduler.add_job(send_weekly_tasks, CronTrigger(day_of_week='mon', hour=11, minute=30), args=[chat_id])
    await message.answer("📅 Щопонеділка о 11:30 я буду надсилати задачі для бару та залу.")

# Список задач
@dp.message_handler(commands=["task"])
async def list_tasks(message: types.Message):
    tasks = await get_tasks(message.chat.id)
    if not tasks:
        await message.answer("✅ У тебе немає активних задач!")
        return
    buttons = [InlineKeyboardButton(text=f"✅ {row['text']}", callback_data=f"done:{row['id']}") for row in tasks]
    markup = InlineKeyboardMarkup().add(*buttons)
    await message.answer("📝 Список задач:", reply_markup=markup)

# Отметка выполнения
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("done:"))
async def mark_done(callback_query: types.CallbackQuery):
    task_id = int(callback_query.data.split(":")[1])
    await remove_task(task_id)
    await bot.answer_callback_query(callback_query.id, text="Задача виконана!")
    await bot.send_message(callback_query.message.chat.id, "✅ Задачу видалено!")

# Еженедельная рассылка
async def send_weekly_tasks(chat_id):
    await bot.send_message(chat_id, "👨‍🍳 ОФІЦІАНТИ: 🧂 Спецовники заповнені?")
    await bot.send_message(chat_id, "🍸 БАРМЕНИ: 🧼 Фільтри чисті?")

# Старт планировщика и базы
async def on_startup(dp):
    await create_tables()
    scheduler.start()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
