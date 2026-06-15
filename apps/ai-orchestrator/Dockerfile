FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app:/app/packages/shared/python

COPY apps/ai-orchestrator/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY packages /app/packages
COPY apps/ai-orchestrator/app /app/app

EXPOSE 8001
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]

