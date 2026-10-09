# Re-Mixed audio worker. ffmpeg decodes uploads; libchromaprint-tools provides fpcalc.
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg libchromaprint-tools \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Run as an unprivileged user.
RUN useradd --create-home worker
USER worker

ENV PORT=8080
EXPOSE 8080
CMD ["sh", "-c", "uvicorn audio_worker.app:app --host 0.0.0.0 --port ${PORT}"]
