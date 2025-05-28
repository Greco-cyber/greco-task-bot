import logging
import os
import asyncpg
import aiohttp
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime

API_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")
WEATHER_API_KEY = "7c50670f4a42d50802416f17b95682e1"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)
scheduler = AsyncIOScheduler()

# Створення таблиць
async def create_tables():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            chat_id BIGINT,
            task TEXT
        );
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS weather_subscribers (
            chat_id BIGINT PRIMARY KEY
        );
    """)
    await conn.close()

# Погодна розсилка
async def get_forecast_message():
    lat, lon = 50.4084, 30.3654
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&units=metric&lang=ua&appid={WEATHER_API_KEY}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            data = await resp.json()
            target_times = ["10:00:00", "13:00:00", "16:00:00", "20:00:00"]
            results = {}
            for entry in data['list']:
                time_str = entry['dt_txt'].split(' ')[1]
                if time_str in target_times:
                    hour = time_str[:2]
                    desc = entry['weather'][0]['description'].capitalize()
                    temp = entry['main']['temp']
                    results[hour] = f"🕒 {hour}:30 — {desc}, {round(temp)}°C"
            msg = "🌤 Прогноз погоди у Софiївськiй Борщагiвцi:\n\n" + "\n".join(results.values())
            return msg

async def send_forecast():
    msg = await get_forecast_message()
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT chat_id FROM weather_subscribers")
    for row in rows:
        await bot.send_message(row['chat_id'], msg)
    await conn.close()

@dp.message_handler(commands=["weather"])
async def send_weather_command(message: types.Message):
    msg = await get_forecast_message()
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("INSERT INTO weather_subscribers (chat_id) VALUES ($1) ON CONFLICT DO NOTHING", message.chat.id)
    await conn.close()
    await message.answer(msg)

@dp.message_handler(commands=["start"])
async def send_welcome(message: types.Message):
    chat_id = message.chat.id
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("INSERT INTO tasks (chat_id, task) VALUES ($1, $2)", chat_id, "Полити каву")
    await conn.execute("INSERT INTO weather_subscribers (chat_id) VALUES ($1) ON CONFLICT DO NOTHING", chat_id)
    await conn.close()
    await message.answer("👋 Привiт! Я бот задач для персоналу ресторану GRECO.")
    await message.answer("🗓️ Щопонедiлка о 11:30 я буду надсилати задачi.\n☀️ А щодня прогноз погоди о 10:30, 13:30, 16:30, 20:30")

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

async def send_weekly_tasks():
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT DISTINCT chat_id FROM tasks")
    for row in rows:
        chat_id = row['chat_id']
        await bot.send_message(chat_id, "👨‍🍳 ОФІЦІАНТИ: 🡢 Спецовники заповнені?")
        await bot.send_message(chat_id, "🍸 БАРМЕНИ: 🧼 Фільтри чисті?")
    await conn.close()

async def on_startup(dp):
    await create_tables()
    scheduler.add_job(send_weekly_tasks, CronTrigger(day_of_week='mon', hour=11, minute=30))
    for h, m in [(10,30), (13,30), (16,30), (20,30)]:
        scheduler.add_job(send_forecast, CronTrigger(hour=h, minute=m))
    scheduler.start()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
