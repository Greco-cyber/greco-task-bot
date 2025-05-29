import logging
import os
import asyncpg
import aiohttp
from aiogram import Bot, Dispatcher, executor, types
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from datetime import datetime

# ENV переменные
BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# Настройка логов
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot, storage=MemoryStorage())
scheduler = AsyncIOScheduler()


class ScheduleForm(StatesGroup):
    recurring = State()
    weekday = State()
    date = State()
    time = State()
    description = State()


async def create_tables():
    conn = await asyncpg.connect(DATABASE_URL)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            chat_id BIGINT,
            task TEXT,
            is_recurring BOOLEAN,
            weekday TEXT,
            date TIMESTAMP,
            time TEXT
        )
    """)
    await conn.close()


@dp.message_handler(commands=['schedule'])
async def cmd_schedule(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("Однократно", "Повтор еженедельно")
    await message.answer("🔁 Обери тип задачі:", reply_markup=kb)
    await ScheduleForm.recurring.set()


@dp.message_handler(state=ScheduleForm.recurring)
async def choose_type(message: types.Message, state: FSMContext):
    choice = message.text.strip()
    if choice == "Повтор еженедельно":
        await state.update_data(recurring=True)
        kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
        kb.add("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        await message.answer("📆 Обери день тижня:", reply_markup=kb)
        await ScheduleForm.weekday.set()
    elif choice == "Однократно":
        await state.update_data(recurring=False)
        await message.answer("📅 Введи дату (YYYY-MM-DD):", reply_markup=types.ReplyKeyboardRemove())
        await ScheduleForm.date.set()
    else:
        await message.answer("❗ Обери один із варіантів.")


@dp.message_handler(state=ScheduleForm.weekday)
async def set_weekday(message: types.Message, state: FSMContext):
    await state.update_data(weekday=message.text.strip())
    await message.answer("🕒 Введи час (HH:MM):")
    await ScheduleForm.time.set()


@dp.message_handler(state=ScheduleForm.date)
async def set_date(message: types.Message, state: FSMContext):
    try:
        dt = datetime.strptime(message.text.strip(), "%Y-%m-%d")
        await state.update_data(date=dt)
        await message.answer("🕒 Введи час (HH:MM):")
        await ScheduleForm.time.set()
    except ValueError:
        await message.answer("❗ Формат дати неправильний. Спробуй знову.")


@dp.message_handler(state=ScheduleForm.time)
async def set_time(message: types.Message, state: FSMContext):
    await state.update_data(time=message.text.strip())
    await message.answer("✍️ Опиши задачу:")
    await ScheduleForm.description.set()


@dp.message_handler(state=ScheduleForm.description)
async def save_task(message: types.Message, state: FSMContext):
    data = await state.get_data()
    chat_id = message.chat.id
    task = message.text.strip()
    time = data["time"]
    conn = await asyncpg.connect(DATABASE_URL)

    if data["recurring"]:
        weekday = data["weekday"]
        await conn.execute("INSERT INTO tasks (chat_id, task, is_recurring, weekday, time) VALUES ($1, $2, TRUE, $3, $4)", chat_id, task, weekday, time)
        scheduler.add_job(send_scheduled_task, CronTrigger(day_of_week=weekday, hour=int(time[:2]), minute=int(time[3:])), args=[chat_id, task])
    else:
        date = data["date"]
        run_time = datetime.combine(date, datetime.strptime(time, "%H:%M").time())
        await conn.execute("INSERT INTO tasks (chat_id, task, is_recurring, date, time) VALUES ($1, $2, FALSE, $3, $4)", chat_id, task, run_time, time)
        scheduler.add_job(send_scheduled_task, DateTrigger(run_date=run_time), args=[chat_id, task])

    await conn.close()
    await message.answer("✅ Задача збережена!", reply_markup=types.ReplyKeyboardRemove())
    await state.finish()


async def send_scheduled_task(chat_id, task):
    await bot.send_message(chat_id, f"🔔 Нагадування: {task}")


async def on_startup(dp):
    await create_tables()
    conn = await asyncpg.connect(DATABASE_URL)
    rows = await conn.fetch("SELECT * FROM tasks")
    for row in rows:
        chat_id = row['chat_id']
        task = row['task']
        time = row['time']
        if row['is_recurring']:
            scheduler.add_job(send_scheduled_task, CronTrigger(day_of_week=row['weekday'], hour=int(time[:2]), minute=int(time[3:])), args=[chat_id, task])
        else:
            scheduler.add_job(send_scheduled_task, DateTrigger(run_date=row['date']), args=[chat_id, task])
    await conn.close()
    scheduler.start()


if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True, on_startup=on_startup)
