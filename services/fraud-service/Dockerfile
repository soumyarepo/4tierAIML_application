# ---- Build stage ----
FROM python:3.11-slim AS builder

WORKDIR /build

# Install compilers needed for scikit-learn (OpenMP, BLAS)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    gfortran \
    libopenblas-dev \
    liblapack-dev \
    && rm -rf /var/lib/apt/lists/*

COPY services/fraud-service/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# ---- Runtime stage ----
FROM python:3.11-slim AS runtime

# Create non-root user for safety
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

WORKDIR /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgomp1 \
    libopenblas0 \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local

# Copy application code
COPY --chown=appuser:appgroup services/fraud-service/app/ ./app/

# Ensure data directory exists for model persistence
RUN mkdir -p /data && chown appuser:appgroup /data

ENV PATH=/home/appuser/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Switch to non-root user
USER appuser

EXPOSE 8004

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]