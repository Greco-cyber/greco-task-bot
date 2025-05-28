import logging
import os
import asyncpg
import aiohttp
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

API_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
WEATHER_API_KEY = "7c50670f4a42d50802416f17b95682e1"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
scheduler = AsyncIOScheduler()

# Создание таблиц
async def create_tables():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            chat_id BIGINT,
            task TEXT
        )
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS weather_subscribers (
            chat_id BIGINT PRIMARY KEY
        )
    """)
    await conn.close()

# Получение погоды
async def fetch_weather():
    lat = 50.4084
    lon = 30.3654
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&units=metric&lang=ua&appid={WEATHER_API_KEY}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            temp = data['main']['temp']
            desc = data['weather'][0]['description'].capitalize()
            msg = f"""🌇 Доброго ранку!

📅 Погода у Софiївськiй Борщагiвцi:
{desc}, {temp}°C"""
            return msg

# Рассылка прогноза всем
async def send_weather():
    msg = await fetch_weather()
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT chat_id FROM weather_subscribers")
    for row in rows:
        await bot.send_message(row['chat_id'], msg)
    await conn.close()

# Команда /start
@dp.message_handler(commands=["start"])
async def send_welcome(message: types.Message):
    chat_id = message.chat.id
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("INSERT INTO tasks (chat_id, task) VALUES ($1, $2)", chat_id, "Полити каву")
    await conn.execute("INSERT INTO weather_subscribers (chat_id) VALUES ($1) ON CONFLICT DO NOTHING", chat_id)
    await conn.close()
    await message.answer("👋 Привiт! Я бот задач для персоналу ресторану GRECO.")
    await message.answer("🗓️ Щопонедiлка о 11:30 я буду надсилати задачi.")
    await message.answer("🌤️ Щодня о 10:00 ти отримуватимеш прогноз погоди.")

# Команда /task
@dp.message_handler(commands=["task"])
async def list_tasks(message: types.Message):
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT task FROM tasks WHERE chat_id = $1", message.chat.id)
    await conn.close()
    if not rows:
        await message.answer("✅ У тебе немає активних задач!")
        return
    tasks = [r['task'] for r in rows]
    buttons = [InlineKeyboardButton(text=f"✅ {t}", callback_data=f"done:{i}") for i, t in enumerate(tasks)]
    markup = InlineKeyboardMarkup().add(*buttons)
    await message.answer("📜 Список задач:", reply_markup=markup)

# Завершение задачи
@dp.callback_query_handler(lambda c: c.data and c.data.startswith("done:"))
async def mark_done(callback_query: types.CallbackQuery):
    idx = int(callback_query.data.split(":")[1])
    chat_id = callback_query.message.chat.id
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT task FROM tasks WHERE chat_id = $1", chat_id)
    if idx < len(rows):
        task = rows[idx]['task']
        await conn.execute("DELETE FROM tasks WHERE chat_id = $1 AND task = $2", chat_id, task)
        await bot.answer_callback_query(callback_query.id, text=f"Задача виконана: {task}")
        await bot.send_message(chat_id, f"✅ Виконано: {task}")
    else:
        await bot.answer_callback_query(callback_query.id, text="Задача не знайдена.")
    await conn.close()

# Команда /weather
@dp.message_handler(commands=["weather"])
async def manual_weather(message: types.Message):
    chat_id = message.chat.id
    msg = await fetch_weather()
    await message.answer(msg)
    # Добавляем в список рассылки
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("INSERT INTO weather_subscribers (chat_id) VALUES ($1) ON CONFLICT DO NOTHING", chat_id)
    await conn.close()

# Задачи по понедельникам
async def send_weekly_tasks():
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT DISTINCT chat_id FROM tasks")
    for row in rows:
        chat_id = row['chat_id']
        await bot.send_message(chat_id, "👨‍🍳 ОФІЦІАНТИ: 🡢 Заповніть спецовники?")
        await bot.send_message(chat_id, "🍸 БАРМЕНИ: 🧼 Фільтр почистили?")
    await conn.close()

# При старте
async def on_startup(dp):
    await create_tables()
    scheduler.add_job(send_weekly_tasks, CronTrigger(day_of_week='mon', hour=11, minute=30))
    scheduler.add_job(send_weather, CronTrigger(hour=10, minute=0))
    scheduler.start()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
