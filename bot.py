
import logging
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

API_TOKEN = os.getenv("BOT_TOKEN")

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(bot)

tasks = {}

@dp.message_handler(commands=["start"])
async def send_welcome(message: types.Message):
    tasks[message.chat.id] = ["Полити каву", "Помий барну стійку"]
    await message.answer("👋 Привіт! Я бот задач для персоналу ресторану GRECO.")

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

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
