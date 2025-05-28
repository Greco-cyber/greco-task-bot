# Используем официальный образ Python 3.10 (легковесный вариант)
FROM python:3.10-slim

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем все файлы проекта в рабочую директорию
COPY . .

# Обновляем pip и устанавливаем зависимости из requirements.txt без кеша
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Команда для запуска бота
CMD ["python", "bot.py"]
