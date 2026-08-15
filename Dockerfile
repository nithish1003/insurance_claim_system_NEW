FROM python:3.11-slim

# Install system dependencies
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

# Environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project source
COPY . .

# Create required directories
RUN mkdir -p /app/static /app/media

# Collect static files during Docker build
RUN SECRET_KEY=build-placeholder python manage.py collectstatic --noinput

# Expose Render default port
EXPOSE 10000

# Start the Django ASGI application with diagnostics
CMD ["sh", "-c", "echo '=== ClaimIQ startup ==='; echo \"PORT=${PORT}\"; python manage.py check; echo '=== Starting Daphne ==='; exec daphne -b 0.0.0.0 -p ${PORT:-10000} insurance_claim_system.asgi:application"]
