# ─────── BUILD STAGE ───────
FROM python:3.10-slim AS builder

# Ensure we can install build-time dependencies (wheels, C headers, etc.)
RUN apt-get update \
 && apt-get install -y --no-install-recommends build-essential gcc \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install only build-time deps and compile wheels into a wheelhouse
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip wheel --no-cache-dir --wheel-dir=/wheels -r requirements.txt

# ─────── RUNTIME STAGE ───────
FROM python:3.10-slim

WORKDIR /app

# Copy just the prebuilt wheels and install only the runtime packages
COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*

# Copy your application code
COPY src/ ./src
COPY main.py .    # or whatever entrypoint you have

# If you have environment variables, set them here:
# ENV PYTHONUNBUFFERED=1

# Finally, tell Docker how to run your app
CMD ["python", "main.py"]
