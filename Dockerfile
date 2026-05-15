FROM python:3.11-slim

WORKDIR /app

# Install deps first for Docker layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Web UI on port 8000
EXPOSE 8000

# Default: run web UI. Override with: docker run agents python3 main.py "task"
CMD ["python3", "web/app.py", "--host", "0.0.0.0", "--port", "8000"]
