FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN useradd --create-home --uid 10001 knowledgeops
COPY pyproject.toml README.md LICENSE_INFORMATION.md ./
COPY backend ./backend
COPY examples ./examples
COPY alembic.ini ./
COPY migrations ./migrations
RUN python -m pip install --upgrade pip && python -m pip install .

RUN mkdir -p /app/data && chown -R knowledgeops:knowledgeops /app
USER knowledgeops

EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && knowledgeops init-db && exec knowledgeops serve --host 0.0.0.0 --port 8000"]
