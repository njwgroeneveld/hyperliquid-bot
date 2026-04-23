FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /data/logs /data/database

ENV LOG_DIR=/data/logs
ENV DATABASE_PATH=/data/bot.db
ENV METRICS_PORT=8080

EXPOSE 8080

CMD ["python", "-m", "src.main"]
