# curl serve ao healthcheck do compose e ao do ECS. Nada de ffmpeg nem de
# modelo de fala: quem baixa e decodifica o áudio é a AssemblyAI, a partir
# da URL presigned — a imagem que substitui o dublê Vosk encolhe bastante.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TRANSCRIPTION_MODE=stub

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY prompts ./prompts

# Clinical service: no reason for the running process to have root. The app
# only ever reads its own files (no writes under /app at runtime — the stub
# is network-free and PROMPTS_DIR is read-only), so switching user after the
# COPY steps costs nothing.
RUN useradd --system --no-create-home --shell /usr/sbin/nologin rafira
USER rafira

EXPOSE 4000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "4000"]
