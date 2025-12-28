FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Build context is project root, so paths are relative to that
COPY services/platform-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/platform-api/app /app/app
COPY services/platform-api/scripts /app/scripts

# Create cashflow_data directory (skip copy if Data directory doesn't exist)
RUN mkdir -p /app/cashflow_data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
