import os

import uvicorn

try:
    # ZeroGPU refuses to start a Space with no @spaces.GPU function.
    # This dummy is never called, so it uses no GPU time.
    import spaces

    @spaces.GPU(duration=1)
    def _dummy_gpu():
        return None
except ImportError:  # running locally, the package only exists on Spaces
    pass

from app.main import app  # noqa: E402,F401

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7860")))
