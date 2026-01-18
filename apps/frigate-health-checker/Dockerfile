# syntax=docker/dockerfile:1

# Build stage - install dependencies with Poetry
FROM python:3.11-slim AS builder

WORKDIR /app

# Install poetry
RUN pip install --no-cache-dir poetry==1.8.5

# Copy dependency files and README (needed for package installation)
COPY pyproject.toml poetry.lock* README.md ./

# Configure poetry to not create virtual env (we're in container)
RUN poetry config virtualenvs.create false

# Install dependencies only first (better layer caching)
RUN poetry install --only=main --no-interaction --no-ansi --no-root

# Copy application code
COPY src/ ./src/

# Install the package itself (creates CLI entrypoint)
RUN poetry install --only=main --no-interaction --no-ansi


# Runtime stage - minimal image
FROM python:3.11-slim AS runtime

WORKDIR /app

# Create non-root user for security
RUN groupadd --gid 1000 appgroup && \
    useradd --uid 1000 --gid appgroup --shell /bin/bash --create-home appuser

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin/frigate-health-checker /usr/local/bin/frigate-health-checker

# Copy source code (needed for the entrypoint)
COPY --from=builder /app/src ./src

# Set ownership
RUN chown -R appuser:appgroup /app

# Switch to non-root user
USER appuser

# Set Python path
ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

# Health check (optional - for debugging)
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "from frigate_health_checker.config import get_settings; print('OK')" || exit 1

# Default entrypoint
ENTRYPOINT ["frigate-health-checker"]
