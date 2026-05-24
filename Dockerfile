FROM python:3.12-slim
RUN pip install --no-cache-dir uv
WORKDIR /app

# deps first (layer cache)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY config.json ./
RUN uv sync --frozen --no-dev

ENV STORAGE_BACKEND=r2 \
    VECTOR_BACKEND=pgvector \
    FAMILY_PHOTOS_ALLOW_MISSING_FRONTEND=1
EXPOSE 8000
CMD ["uv", "run", "uvicorn", "app.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
