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
WEATHER_API_KEY = os.getenv("WEATHER_API_KEY") or "7c50670f4a42d50802416f17b95682e1"

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
        );
    """)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS weather_subscribers (
            chat_id BIGINT PRIMARY KEY
        );
    """)
    await conn.close()

# Получение прогноза погоды
async def get_forecast():
    lat, lon = 50.4084, 30.3654  # Софиевская Борщаговка
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&units=metric&lang=ua&appid={WEATHER_API_KEY}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

# Отправка прогноза
async def send_forecast():
    data = await get_forecast()
    if "list" not in data:
        return

    intervals = ["12:00:00", "15:00:00", "18:00:00", "21:00:00"]
    today = datetime.utcnow().date().isoformat()

    forecasts = [entry for entry in data['list']
                 if entry['dt_txt'].startswith(today)
                 and any(t in entry['dt_txt'] for t in intervals)]

    if not forecasts:
        return

    msg = "\u2600\ufe0f\u043f\u0440\u043e\u0433\u043d\u043e\u0437 \u043f\u043e\u0433\u043e\u0434\u0438 \u0443 \u0421\u043e\u0444\u0456\u0457\u0432\u0441\u044c\u043a\u0456\u0439 \u0411\u043e\u0440\u0449\u0430\u0433\u0456\u0432\u0446\u0456:\n\n"
    for forecast in forecasts:
        time = forecast['dt_txt'][11:16]
        temp = forecast['main']['temp']
        desc = forecast['weather'][0]['description'].capitalize()
        msg += f"{time} — {desc}, {temp:.1f}°C\n"

    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT chat_id FROM weather_subscribers")
    for row in rows:
        await bot.send_message(row['chat_id'], msg)
    await conn.close()

@dp.message_handler(commands=["start"])
async def send_welcome(message: types.Message):
    chat_id = message.chat.id
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("INSERT INTO tasks (chat_id, task) VALUES ($1, $2)", chat_id, "Полити каву")
    await conn.execute("INSERT INTO weather_subscribers (chat_id) VALUES ($1) ON CONFLICT DO NOTHING", chat_id)
    await conn.close()
    await message.answer("\U0001F44B Привіт! Я бот задач для персоналу ресторану GRECO.")
    await message.answer("\ud83d\uddd3\ufe0f Щопонеділка о 11:30 я буду надсилати задачі, а прогноз погоди щодня о 10:30, 13:30, 16:30, 20:30.")

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

@dp.message_handler(commands=["weather"])
async def send_weather_command(message: types.Message):
    await send_forecast()
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("INSERT INTO weather_subscribers (chat_id) VALUES ($1) ON CONFLICT DO NOTHING", message.chat.id)
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
    for hour in [10, 13, 16, 19]:
        scheduler.add_job(send_forecast, CronTrigger(hour=hour, minute=30))
    scheduler.start()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
