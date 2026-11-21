"""Tareas CPU de preparación y CI, separadas de la función GPU."""

from __future__ import annotations

from pathlib import Path
import os

import modal

from deploy.modal_config import deployment_environment, load_deployment_model


LOCAL_ROOT = Path(__file__).resolve().parent
MODEL = load_deployment_model()
MODEL_CACHE = "/models/huggingface"

app = modal.App("biblioteca-agent-tasks")
model_volume = modal.Volume.from_name(
    "biblioteca-model-cache",
    create_if_missing=True,
)

download_image = (
    modal.Image.debian_slim(python_version="3.11")
    .uv_pip_install("huggingface_hub==0.36.0")
    .add_local_dir(LOCAL_ROOT / "deploy", "/root/deploy", copy=True)
    .env({"HF_HOME": MODEL_CACHE, **deployment_environment(MODEL)})
)

@app.function(
    image=download_image,
    volumes={"/models": model_volume},
    timeout=3600,
    cpu=2,
    memory=4096,
    secrets=[modal.Secret.from_name(os.environ["MODAL_HF_SECRET"])] if os.getenv("MODAL_HF_SECRET") else [],
)
def download_model() -> dict[str, str]:
    """Descarga pesos con CPU antes de iniciar una GPU facturable."""
    from huggingface_hub import snapshot_download

    print(f"Preparando checkpoint: {MODEL.checkpoint}", flush=True)
    path = snapshot_download(repo_id=MODEL.checkpoint)
    model_volume.commit()
    return {"model": MODEL.checkpoint, "cache_path": path}


