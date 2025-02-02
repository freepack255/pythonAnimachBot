# ================================
# Stage 1: builder
# ================================
FROM python:3.13-slim-bookworm AS builder

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Copy only requirements to leverage Docker cache
COPY requirements.txt .

# Install build dependencies and Python packages
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get purge -y --auto-remove gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

# ================================
# Stage 2: final
# ================================
FROM python:3.13-slim-bookworm

# Set environment variables for Python
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

WORKDIR /app

# Copy installed packages from builder (system-wide installation)
COPY --from=builder /usr/local /usr/local

# Copy your source code
COPY . /app

# Create a non-root user and switch to it
RUN useradd -m app
USER app

# Optionally expose a port if needed (e.g., for a webhook)
# EXPOSE 8080

CMD ["python", "-m", "animachpostingbot.main"]
