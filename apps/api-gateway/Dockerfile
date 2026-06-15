FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app:/app/packages/shared/python

COPY apps/api-gateway/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY packages /app/packages
COPY apps/api-gateway/app /app/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

