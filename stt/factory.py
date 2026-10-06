"""STT backend selector. Switch engines via STT_BACKEND in .env."""
import os

from .deepgram import DeepgramTranscriber


def create_transcriber():
    backend = os.getenv("STT_BACKEND", "deepgram").strip().lower()

    if backend == "deepgram":
        import config
        return DeepgramTranscriber(
            api_key=config.deepgram_api_key(),
            model=config.deepgram_model(),
            language=config.deepgram_language(),
        )

    if backend == "parakeet":
        from .parakeet import ParakeetTranscriber

        binary = os.getenv("PARAKEET_BINARY", "").strip()
        model = os.getenv("PARAKEET_MODEL", "").strip()
        if not binary or not model:
            raise RuntimeError(
                "Missing PARAKEET_BINARY or PARAKEET_MODEL in .env."
            )
        return ParakeetTranscriber(binary_path=binary, model_path=model)

    raise ValueError(f"Unsupported STT backend: {backend!r}")


def create_stream_session(on_partial=None):
    """Started streaming session for toggle-to-talk.

    deepgram -> FluxStreamer (cloud), parakeet_stream -> ParakeetStreamSession
    (local 120M EOU). Batch-only backends (parakeet) raise here.
    """
    backend = os.getenv("STT_BACKEND", "deepgram").strip().lower()

    if backend == "deepgram":
        import config
        from .flux import FluxStreamer

        session = FluxStreamer(
            api_key=config.deepgram_api_key(),
            model=config.deepgram_flux_model(),
        )
    elif backend == "parakeet_stream":
        import config
        from .parakeet_stream import ParakeetStreamSession

        session = ParakeetStreamSession(
            binary_path=config.parakeet_stream_binary(),
            model_path=config.parakeet_stream_model(),
        )
    else:
        raise ValueError(
            f"Backend {backend!r} has no streaming mode; "
            "toggle uses batch recording for it."
        )

    session.start(on_partial=on_partial)
    return session
