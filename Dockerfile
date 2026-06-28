FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install dependencies (leveraging layer cache)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application
COPY . .

# Create a directory for the persistent database
RUN mkdir -p /data

# Tell the bot to store the SQLite file inside /data
ENV DB_PATH=/data/bot_data.sqlite

# Declare volume for persistence
VOLUME ["/data"]

# The token must be provided via docker run / compose
ENV TELEGRAM_BOT_TOKEN=""

CMD ["python", "boardgame_poll_bot.py"]
