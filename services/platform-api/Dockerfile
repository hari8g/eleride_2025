FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Build context is project root, so paths are relative to that
COPY services/platform-api/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY services/platform-api/app /app/app
COPY services/platform-api/scripts /app/scripts

# Create cashflow_data directory and copy data files
# Copy the Data directory using a shell glob that handles the space
RUN mkdir -p /app/cashflow_data
# Use a shell command to find and copy the data
COPY ["Cash flow_underwriting/Data", "/tmp/cashflow_data_src/"]
RUN cp -r /tmp/cashflow_data_src/* /app/cashflow_data/ && \
    echo "✅ Copied cashflow data files" && \
    ls -1 /app/cashflow_data | wc -l && \
    rm -rf /tmp/cashflow_data_src

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
