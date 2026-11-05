FROM python:3.12-slim

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"

RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libreoffice-writer \
    tesseract-ocr \
    tesseract-ocr-rus \
    tesseract-ocr-eng \
    tesseract-ocr-kat \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
