FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HOME=/home/user/.cache/huggingface \
    PORT=7860

# Hugging Face Spaces runs containers as uid 1000
RUN useradd -m -u 1000 user
WORKDIR /home/user/app

COPY --chown=user requirements.txt .
RUN pip install -r requirements.txt

USER user
ARG WHISPER_MODEL=small
ENV WHISPER_MODEL=${WHISPER_MODEL}
# Bake the model into the image so cold starts don't download it
RUN python -c "from faster_whisper import download_model; download_model('${WHISPER_MODEL}')"

COPY --chown=user . .

EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
