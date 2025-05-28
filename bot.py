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

# Прогноз погоды по интервалам
async def get_weather_forecast():
    lat = 50.4084
    lon = 30.3654
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&units=metric&lang=ua&appid={WEATHER_API_KEY}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            return await response.json()

async def send_weather_forecast(chat_id):
    forecast = await get_weather_forecast()
    intervals = ["10:30", "13:30", "16:30", "20:30"]
    targets = [f"{datetime.now().date()} {t}:00" for t in intervals]
    msg = "\u2600\ufe0f\uFE0F Прогноз погоди у Софіївській Борщагівці:\n"
    found = False

    for entry in forecast.get("list", []):
        dt_txt = entry.get("dt_txt")
        if dt_txt and any(t in dt_txt for t in targets):
            temp = entry['main']['temp']
            desc = entry['weather'][0]['description'].capitalize()
            time = dt_txt.split()[1][:5]
            msg += f"\n<b>{time}</b>: {desc}, {temp}°C"
            found = True

    if not found:
        msg += "\n(на жаль, прогноз недоступний на обрані години)"

    await bot.send_message(chat_id, msg, parse_mode="HTML")

# Команда /start
@dp.message_handler(commands=["start"])
async def send_welcome(message: types.Message):
    chat_id = message.chat.id
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("INSERT INTO tasks (chat_id, task) VALUES ($1, $2)", chat_id, "Полити каву")
    await conn.execute("INSERT INTO weather_subscribers (chat_id) VALUES ($1) ON CONFLICT DO NOTHING", chat_id)
    await conn.close()
    await message.answer("\ud83d\udc4b Привіт! Я бот задач для персоналу ресторану GRECO.")
    await message.answer("\ud83d\uddd3\ufe0f Щопонеділка о 11:30 я буду надсилати задачі.\n\u2600\ufe0f І щодня - прогноз погоди.")

# Команда /task
@dp.message_handler(commands=["task"])
async def list_tasks(message: types.Message):
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT task FROM tasks WHERE chat_id = $1", message.chat.id)
    await conn.close()
    if not rows:
        await message.answer("\u2705 У тебе немає активних задач!")
        return
    tasks = [r['task'] for r in rows]
    buttons = [InlineKeyboardButton(text=f"\u2705 {t}", callback_data=f"done:{i}") for i, t in enumerate(tasks)]
    markup = InlineKeyboardMarkup().add(*buttons)
    await message.answer("\ud83d\udccb Список задач:", reply_markup=markup)

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
        await bot.send_message(chat_id, f"\u2705 Виконано: {task}")
    else:
        await bot.answer_callback_query(callback_query.id, text="Задача не знайдена.")
    await conn.close()

# Команда /weather
@dp.message_handler(commands=["weather"])
async def send_weather_command(message: types.Message):
    chat_id = message.chat.id
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("INSERT INTO weather_subscribers (chat_id) VALUES ($1) ON CONFLICT DO NOTHING", chat_id)
    await conn.close()
    await send_weather_forecast(chat_id)

# Рассылка задач
async def send_weekly_tasks():
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT DISTINCT chat_id FROM tasks")
    for row in rows:
        chat_id = row['chat_id']
        await bot.send_message(chat_id, "\ud83d\udc68\u200d\ud83c\udf73 ОФІЦІАНТИ: \ud83d\udd22 Спецовники заповнені?")
        await bot.send_message(chat_id, "\ud83c\udf78 БАРМЕНИ: \ud83e\ude9c Фільтри чисті?")
    await conn.close()

# Рассылка прогноза погоды
async def send_morning_weather():
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT chat_id FROM weather_subscribers")
    await conn.close()
    for row in rows:
        await send_weather_forecast(row['chat_id'])

async def on_startup(dp):
    await create_tables()
    scheduler.add_job(send_weekly_tasks, CronTrigger(day_of_week='mon', hour=11, minute=30))
    scheduler.add_job(send_morning_weather, CronTrigger(hour=10, minute=0))
    scheduler.start()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
