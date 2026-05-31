# Multi-arch: build for arm64/amd64 with
#   docker buildx build --platform linux/amd64,linux/arm64 -t agents .
FROM python:3.11-slim

WORKDIR /app

# Install deps first for Docker layer cache
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Web UI on port 8000
EXPOSE 8000

# Healthcheck hits the web UI (stdlib urllib only — no extra packages).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=4).status < 500 else 1)" || exit 1

# Default: run web UI. Override with: docker run agents python3 main.py "task"
CMD ["python3", "web/app.py", "--host", "0.0.0.0", "--port", "8000"]
