FROM python:3.13-slim

WORKDIR /app

# system deps (small set; pandas wheels available)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY scripts/ /app/scripts/
COPY frontend/ /app/frontend/
COPY outputs/ /app/outputs/
COPY outputs_underwriting/ /app/outputs_underwriting/

EXPOSE 8080

# Build dashboard.json from latest outputs and serve the SPA
CMD ["bash", "-lc", "python -u scripts/build_dashboard_json.py --root . --out frontend/data/dashboard.json && python -u scripts/serve_dashboard.py --dir frontend --host 0.0.0.0 --port 8080"]


