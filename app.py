"""Entry point for Hugging Face Spaces (Gradio SDK, ZeroGPU hardware) and `python app.py` locally.

Our FastAPI app (REST + WebSocket + UI) is served at "/".
A tiny hidden Gradio app with an @spaces.GPU function is mounted at /gradio so that
ZeroGPU's startup check finds a GPU function registered through Gradio's normal startup path.
"""
import os

import uvicorn

from app.main import app as api_app

app = api_app

try:
    import gradio as gr

    try:
        import spaces

        @spaces.GPU(duration=1)
        def gpu_ping(x: str = "") -> str:  # never used for real work, so it costs no GPU time
            return "ok"
    except ImportError:  # `spaces` only exists on Hugging Face
        def gpu_ping(x: str = "") -> str:
            return "ok"

    with gr.Blocks(title="GPU ping") as demo:
        gr.Markdown("Backend helper. The app UI is at `/`.")
        box = gr.Textbox(visible=False)
        btn = gr.Button("ping", visible=False)
        btn.click(gpu_ping, box, box, api_name="gpu_ping")

    app = gr.mount_gradio_app(api_app, demo, path="/gradio")
except ImportError:  # gradio not installed locally: serve the plain API app
    pass

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "7860")))
