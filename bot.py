import logging
import os
import asyncpg
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

API_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

scheduler = AsyncIOScheduler()
scheduler.start()

async def create_tables():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id SERIAL PRIMARY KEY,
            chat_id BIGINT,
            task TEXT
        );
    """)
    await conn.close()

@dp.message_handler(commands=["start"])
async def send_welcome(message: types.Message):
    chat_id = message.chat.id
    await message.answer("👋 Привіт! Я бот задач для персоналу ресторану GRECO.")
    scheduler.add_job(send_weekly_tasks, CronTrigger(day_of_week='mon', hour=11, minute=30), args=[chat_id])
    await message.answer("📅 Щопонеділка о 11:30 я буду надсилати задачі для бару та залу.")

@dp.message_handler(commands=["task"])
async def list_tasks(message: types.Message):
    chat_id = message.chat.id
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT id, task FROM tasks WHERE chat_id = $1", chat_id)
    await conn.close()
    if not rows:
        await message.answer("✅ У тебе немає активних задач!")
        return
    buttons = [InlineKeyboardButton(text=f"✅ {r['task']}", callback_data=f"done:{r['id']}") for r in rows]
    markup = InlineKeyboardMarkup().add(*buttons)
    await message.answer("📝 Список задач:", reply_markup=markup)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("done:"))
async def mark_done(callback_query: types.CallbackQuery):
    task_id = int(callback_query.data.split(":")[1])
    conn = await asyncpg.connect(DATABASE_URL)
    task = await conn.fetchrow("DELETE FROM tasks WHERE id = $1 RETURNING task", task_id)
    await conn.close()
    if task:
        await bot.answer_callback_query(callback_query.id, text=f"Задача виконана: {task['task']}")
        await bot.send_message(callback_query.message.chat.id, f"✅ Виконано: {task['task']}")
    else:
        await bot.answer_callback_query(callback_query.id, text="Задача не знайдена.")

async def send_weekly_tasks(chat_id):
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.executemany("INSERT INTO tasks(chat_id, task) VALUES($1, $2)", [
        (chat_id, "👨‍🍳 ОФІЦІАНТИ: 🧂 Спецовники заповнені?"),
        (chat_id, "🍸 БАРМЕНИ: 🧼 Фільтри чисті?")
    ])
    await conn.close()
    await bot.send_message(chat_id, "Задачі додані. Використай /task щоб переглянути.")

if __name__ == '__main__':
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(create_tables())
    executor.start_polling(dp, skip_updates=True)
