
import logging
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

API_TOKEN = os.getenv("BOT_TOKEN")
logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

tasks = {}
scheduler = AsyncIOScheduler()
scheduler.start()

@dp.message_handler(commands=["start"])
async def send_welcome(message: types.Message):
    chat_id = message.chat.id
    tasks[chat_id] = ["Полити каву", "Помий барну стійку"]
    await message.answer("👋 Привіт! Я бот задач для персоналу ресторану GRECO.")

    # Добавляем планировщик для текущего пользователя
    scheduler.add_job(send_weekly_tasks, CronTrigger(day_of_week='mon', hour=11, minute=30), args=[chat_id])
    await message.answer("📅 Щопонеділка о 11:30 я буду надсилати задачі для бару та залу.")

@dp.message_handler(commands=["task"])
async def list_tasks(message: types.Message):
    user_tasks = tasks.get(message.chat.id, [])
    if not user_tasks:
        await message.answer("✅ У тебе немає активних задач!")
        return
    buttons = [InlineKeyboardButton(text=f"✅ {t}", callback_data=f"done:{i}") for i, t in enumerate(user_tasks)]
    markup = InlineKeyboardMarkup().add(*buttons)
    await message.answer("📝 Список задач:", reply_markup=markup)

@dp.callback_query_handler(lambda c: c.data and c.data.startswith("done:"))
async def mark_done(callback_query: types.CallbackQuery):
    idx = int(callback_query.data.split(":")[1])
    chat_id = callback_query.message.chat.id
    if chat_id in tasks and len(tasks[chat_id]) > idx:
        task = tasks[chat_id].pop(idx)
        await bot.answer_callback_query(callback_query.id, text=f"Задача виконана: {task}")
        await bot.send_message(chat_id, f"✅ Виконано: {task}")
    else:
        await bot.answer_callback_query(callback_query.id, text="Задача не знайдена.")

async def send_weekly_tasks(chat_id):
    await bot.send_message(chat_id, "👨‍🍳 ОФІЦІАНТИ: 🧂 Спецовники заповнені?")
    await bot.send_message(chat_id, "🍸 БАРМЕНИ: 🧼 Фільтри чисті?")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
