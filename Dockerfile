# KRAKADYL demo backend.
#
# Build:  docker build -t krakadyl-api .
# Run:    docker run -p 8000:8000 \
#           -e KRAKADYL_OPERATOR_TOKENS='<identity=sha256,...>' \
#           -e META_API_KEY='<key>' \
#           -e KRAKADYL_ENABLE_SAM=1 \
#           -e KRAKADYL_CORS_ORIGINS='https://<your-vercel-app>.vercel.app' \
#           krakadyl-api
#
# Single worker on purpose: the store is one SQLite connection and the
# receipt-append protocol serializes inside it (see TECHNICAL_README.md
# "Multi-worker serving" non-goal). Ephemeral /data is fine for a demo:
# the seeded case is recreated at startup, so a restart resets the demo
# to a clean state instead of corrupting it.
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    KRAKADYL_DATA_DIR=/data

RUN pip install uv==0.12.2

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --extra api --no-dev
COPY krakadyl ./krakadyl

EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "krakadyl.api.app:app", \
     "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
