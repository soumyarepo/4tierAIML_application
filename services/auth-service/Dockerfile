# syntax=docker/dockerfile:1
FROM python:3.11-slim AS builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY services/auth-service/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ------------------------------------------------------------------
# Runtime stage
# ------------------------------------------------------------------
FROM python:3.11-slim

WORKDIR /app

# Create non-root user for security
RUN groupadd --gid 1000 appgroup \
    && useradd --uid 1000 --gid appgroup --shell /bin/bash appuser

# Copy installed Python packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy the shared library and application source
COPY --chown=appuser:appgroup src/shared /app/src/shared
COPY --chown=appuser:appgroup services/auth-service/app /app/app

# Set Python path so 'from shared' resolves correctly
ENV PYTHONPATH=/app/src:${PYTHONPATH}
ENV SERVICE_NAME=auth-service

# Expose service port
EXPOSE 8001

# Run as non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8001/health')" || exit 1

ENTRYPOINT ["python", "-m", "uvicorn"]
CMD ["app.main:app", "--host", "0.0.0.0", "--port", "8001"]