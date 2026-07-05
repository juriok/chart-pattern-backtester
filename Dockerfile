FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py live.py main.py dashboard.py ./
COPY data/ ./data/
COPY patterns/ ./patterns/
COPY backtest/ ./backtest/
COPY report/ ./report/

# state/ (paper equity + trade log) is a volume — see docker-compose.yml
CMD ["python", "-u", "live.py"]
