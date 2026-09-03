FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    POSTMEET_WHISPER_MODEL=small \
    POSTMEET_WHISPER_DEVICE=cpu \
    POSTMEET_WHISPER_COMPUTE=int8

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app
RUN python -m pip install --upgrade pip \
 && pip install -e '.[all]'

ENTRYPOINT ["postmeet"]
CMD ["--help"]
