FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Tesseract OCR and its English language data.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-eng \
        passwd \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies.
COPY requirements.txt ./

RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt \
    && tesseract --version \
    && tesseract --list-langs

# Run the application as a non-root user.
RUN groupadd --system appuser \
    && useradd --system \
        --gid appuser \
        --create-home \
        --shell /usr/sbin/nologin \
        appuser

COPY --chown=appuser:appuser . .

USER appuser

EXPOSE 10000

CMD ["sh", "-c", "exec uvicorn main:app --host 0.0.0.0 --port ${PORT:-10000}"]
