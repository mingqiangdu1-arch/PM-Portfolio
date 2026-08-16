FROM python:3.13.5-slim

ARG PIP_INDEX_URL=https://pypi.org/simple
ENV PIP_INDEX_URL=${PIP_INDEX_URL}

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY services/api/pyproject.toml services/api/README.md ./services/api/
COPY services/api/app ./services/api/app
COPY infra/migrations ./infra/migrations

RUN python -m pip install --upgrade "pip==25.1.1" && \
    python -m pip install ./services/api

RUN addgroup --system app && adduser --system --ingroup app app

USER app

CMD ["python", "-m", "alembic", "-c", "infra/migrations/alembic.ini", "upgrade", "head"]
