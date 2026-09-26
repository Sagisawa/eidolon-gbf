FROM python:3.11-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/app/.venv

WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY src ./src
RUN uv sync --frozen --no-dev
# Pipecat splits the character's replies into sentences for TTS with NLTK's punkt tokenizer.
ENV NLTK_DATA=/app/nltk_data
RUN /app/.venv/bin/python -m nltk.downloader -d /app/nltk_data punkt_tab

# On the PATH so that the admin can run `docker compose exec backend eidolon ...`.
ENV PATH=/app/.venv/bin:$PATH \
    EIDOLON_DATABASE_PATH=/data/eidolon.db \
    EIDOLON_CHARACTERS_PATH=/characters/characters.toml \
    EIDOLON_STORY_PATH=/corpus/SCTranslationData/data/story \
    EIDOLON_MIRROR_CACHE_PATH=/data/mirror \
    EIDOLON_EVENT_NAMES_PATH=/deploy/event-names.toml
EXPOSE 8000
CMD ["eidolon"]
