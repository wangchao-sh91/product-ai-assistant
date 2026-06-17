FROM python:3.14-slim

WORKDIR /app
ENV PYTHONPATH=/app:/app/packages/shared/python

COPY apps/ingestion-worker/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY packages /app/packages
COPY apps/ingestion-worker/app /app/app

CMD ["python", "-m", "app.main"]
