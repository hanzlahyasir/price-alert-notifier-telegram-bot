# ─────── BUILD STAGE ───────
FROM python:3.10-slim AS builder

# Install build-time dependencies (C headers, compiler)
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential gcc \
 && rm -rf /var/lib/apt/lists/*

# Set working directory for build
WORKDIR /app

# Copy requirements and build wheels
COPY requirements.txt ./
RUN pip install --upgrade pip \
 && pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt

# ─────── RUNTIME STAGE ───────
FROM python:3.10-slim

# Switch to non-root user if desired (optional)
# RUN useradd --create-home appuser && chown -R appuser /app
# USER appuser

# Set working directory for runtime
WORKDIR /app

# Install only the prebuilt wheels
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/* \
 && rm -rf /wheels

# Copy application code into /app
# Ensure main.py exists alongside Dockerfile in build context
COPY src/ ./src
COPY main.py ./

# (Optional) set environment variables
ENV PYTHONUNBUFFERED=1

# Default command
CMD ["python", "main.py"]
