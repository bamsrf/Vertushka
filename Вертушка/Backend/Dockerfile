# Dockerfile для Вертушка API
FROM python:3.11-slim

# Установка зависимостей системы
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Рабочая директория
WORKDIR /app

# Копирование зависимостей
COPY requirements.txt .

# Установка Python зависимостей
RUN pip install --no-cache-dir -r requirements.txt

# Копирование кода приложения
COPY . .

# Создание директорий для статики
RUN mkdir -p app/web/static/css app/web/static/js app/web/templates

# Порт приложения
EXPOSE 8000

# Запуск приложения
# --proxy-headers: корректные scheme/proto за nginx (X-Forwarded-Proto). Бэкенд-порт
# не публикуется наружу (доступен только nginx по docker-сети). IP клиента для
# rate-limit берётся отдельно через X-Real-IP (см. app/utils/request_ip.py).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]

