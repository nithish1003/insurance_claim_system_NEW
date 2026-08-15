# ClaimIQ Production Dockerfile
FROM python:3.11-slim

# System dependencies for PostgreSQL, Tesseract OCR, and OpenCV
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    tesseract-ocr \
    ffmpeg \
    libsm6 \
    libxext6 \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python environment
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source
COPY . .

# Collect static files into STATIC_ROOT (BASE_DIR / "staticfiles")
RUN SECRET_KEY=build-placeholder python manage.py collectstatic --noinput

# Expose the port Render will bind to
EXPOSE 10000

# Start Daphne ASGI server (supports HTTP + WebSockets)
CMD ["sh", "-c", "daphne -b 0.0.0.0 -p ${PORT:-10000} insurance_claim_system.asgi:application"]
