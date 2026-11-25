import os


def _normalize_db_url(url: str) -> str:
    # Heroku/Neon style "postgres://" is not understood by SQLAlchemy 2.x
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url


class Settings:
    database_url: str = _normalize_db_url(os.getenv("DATABASE_URL", "sqlite:///./data/app.db"))

    # "whisper" (faster-whisper, open source) or "mock"
    stt_engine: str = os.getenv("STT_ENGINE", "whisper").lower()
    whisper_model: str = os.getenv("WHISPER_MODEL", "small")
    whisper_compute_type: str = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
    whisper_beam_size: int = int(os.getenv("WHISPER_BEAM_SIZE", "2"))
    # Languages the auto-detector may choose between (mixed Hindi + English use case)
    allowed_languages: tuple = tuple(os.getenv("ALLOWED_LANGUAGES", "hi,en").split(","))

    # Streaming / endpointing
    partial_every_seconds: float = float(os.getenv("PARTIAL_EVERY_SECONDS", "1.0"))
    silence_end_seconds: float = float(os.getenv("SILENCE_END_SECONDS", "0.8"))
    max_utterance_seconds: float = float(os.getenv("MAX_UTTERANCE_SECONDS", "20"))
    max_session_seconds: float = float(os.getenv("MAX_SESSION_SECONDS", "900"))
    min_speech_rms: float = float(os.getenv("MIN_SPEECH_RMS", "0.012"))


settings = Settings()

# Prompt that nudges Whisper towards Hindi (Devanagari) + English (Latin) code-mixed output
HINGLISH_PROMPT = "नमस्ते, how are you? मैं आज office जा रहा हूँ, meeting at 5 बजे है."
