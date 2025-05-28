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

# Создание таблицы
async def create_tables():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            chat_id BIGINT,
            task TEXT
        )
    """)
    await conn.close()

# Прогноз на ближайшие интервалы
async def get_weather_forecast():
    lat, lon = 50.4084, 30.3654
    url = f"https://api.openweathermap.org/data/2.5/forecast?lat={lat}&lon={lon}&units=metric&lang=ua&appid={WEATHER_API_KEY}"

    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
            forecast_list = data["list"]

            intervals = ["10:30", "13:30", "16:30", "20:30"]
            today = datetime.now().date()
            result = []

            for entry in forecast_list:
                dt = datetime.fromtimestamp(entry["dt"])
                if dt.date() == today:
                    hour_min = dt.strftime("%H:%M")
                    if hour_min in intervals:
                        temp = round(entry["main"]["temp"])
                        desc = entry["weather"][0]["description"].capitalize()
                        result.append(f"{hour_min} – {desc}, {temp}°C")

            if not result:
                return "⚠️ Прогноз на сьогодні недоступний."
            return "📅 Прогноз погоди на сьогодні:\n" + "\n".join(result)

# Рассылка прогноза по команде
@dp.message_handler(commands=["weather"])
async def send_weather_command(message: types.Message):
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT 1 FROM tasks WHERE chat_id = $1", message.chat.id)
    if not rows:
        await conn.execute("INSERT INTO tasks (chat_id, task) VALUES ($1, $2)", message.chat.id, "weather auto")
    await conn.close()

    forecast = await get_weather_forecast()
    await message.answer(forecast)

# Приветствие
@dp.message_handler(commands=["start"])
async def send_welcome(message: types.Message):
    chat_id = message.chat.id
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("INSERT INTO tasks (chat_id, task) VALUES ($1, $2)", chat_id, "Полити каву")
    await conn.close()
    await message.answer("👋 Привiт! Я бот задач для персоналу ресторану GRECO.")
    await message.answer("🗓️ Щопонедiлка о 11:30 я буду надсилати задачi.")

# Список задач
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

# Завершение задач
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

# Автоматические задачи
async def send_weekly_tasks():
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT DISTINCT chat_id FROM tasks")
    for row in rows:
        chat_id = row['chat_id']
        await bot.send_message(chat_id, "👨‍🍳 ОФІЦІАНТИ: 🡢 Спецовники заповнені?")
        await bot.send_message(chat_id, "🍸 БАРМЕНИ: 🧼 Фільтри чисті?")
    await conn.close()

# Автоматическая погода в 10:00
async def send_morning_weather():
    forecast = await get_weather_forecast()
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT DISTINCT chat_id FROM tasks")
    for row in rows:
        await bot.send_message(row['chat_id'], forecast)
    await conn.close()

# Запуск
async def on_startup(dp):
    await create_tables()
    scheduler.add_job(send_weekly_tasks, CronTrigger(day_of_week='mon', hour=11, minute=30))
    scheduler.add_job(send_morning_weather, CronTrigger(hour=10, minute=0))
    scheduler.start()

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
