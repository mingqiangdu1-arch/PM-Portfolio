FROM python:3.13.5-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
RUN python -m pip install --upgrade "pip==25.1.1" && \
    python -m pip install .

RUN addgroup --system app && adduser --system --ingroup app app
USER app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
