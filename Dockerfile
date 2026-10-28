# Use official lightweight Python image
FROM python:3.12-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Set working directory inside container
WORKDIR /app

# Install system dependencies needed for PostgreSQL and compilation
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app/

# Expose Gunicorn port
EXPOSE 8000

# Default startup command (Gunicorn WSGI server)
CMD ["sh", "-c", "python manage.py migrate && (python manage.py createsuperuser --noinput || true) && exec gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 3"]