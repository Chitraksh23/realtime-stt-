import os

import uvicorn

try:  # satisfies ZeroGPU's startup check if the Space is on ZeroGPU hardware
    import spaces

    @spaces.GPU
    def _noop():
        return None
except ImportError:
    pass

from app.main import app  # noqa: E402,F401

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7860")))
