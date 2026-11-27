"""Despliegue Modal: API del agente y vLLM en una sola réplica GPU.

Modal expone únicamente el puerto de FastAPI. vLLM escucha en loopback, por lo
que el adaptador OpenAI existente se reutiliza sin publicar un segundo servicio.
"""

from __future__ import annotations

import os
import sys
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

LOCAL_ROOT = Path("/app") if Path("/app/SKILL.md").is_file() else Path(__file__).resolve().parents[2]
sys.path.insert(0, str(LOCAL_ROOT))

import modal

from deploy.model_config import build_vllm_command, deployment_environment
from deploy.modal.profile import load_cloud_gpus, load_cloud_model


MODEL = load_cloud_model(LOCAL_ROOT)
VLLM_VERSION = "0.11.0"
TRANSFORMERS_VERSION = "4.57.1"
VLLM_PORT = 8000
AGENT_PORT = 8001
MODEL_CACHE = "/models/huggingface"

app = modal.App(f"biblioteca-agent-{MODEL.name}")
model_volume = modal.Volume.from_name(
    "biblioteca-model-cache",
    create_if_missing=True,
)

server_image = (
    modal.Image.from_dockerfile(
        LOCAL_ROOT / "Dockerfile",
        context_dir=LOCAL_ROOT,
    )
    .apt_install("gcc", "g++")
    .uv_pip_install(
        f"vllm=={VLLM_VERSION}",
        f"transformers=={TRANSFORMERS_VERSION}",
    )
    .add_local_dir(LOCAL_ROOT / "deploy", "/app/deploy", copy=True)
    .env(
        {
            **deployment_environment(MODEL),
            "AGENT_CLASSIFICATION_MODE": os.getenv("AGENT_CLASSIFICATION_MODE", "stable"),
            "HF_HOME": MODEL_CACHE,
            "AGENT_VLLM_BASE_URL": f"http://127.0.0.1:{VLLM_PORT}/v1",
            "AGENT_VLLM_API_KEY": "local-loopback",
            "AGENT_CATALOG_SNAPSHOT": "",
            "RAG_DB_PATH": "/tmp/biblioteca/rag.sqlite3",
            "AUTO_INDEX_RAG": "true",
            "VLLM_MAX_TOKENS": "384",
            "AGENT_MAX_CONCURRENCY": "4",
            "PORT": str(AGENT_PORT),
            "PORT_HEALTH": str(AGENT_PORT),
        }
    )
)


def _wait_for_http(url: str, process: subprocess.Popen[bytes], timeout: int) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"El proceso terminó antes de responder en {url} (código {process.returncode})."
            )
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if response.status == 200:
                    return
        except (OSError, urllib.error.URLError):
            time.sleep(1)
    raise TimeoutError(f"El servicio no respondió a tiempo en {url}.")


@app.server(
    image=server_image,
    cpu=4,
    memory=16384,
    gpu=load_cloud_gpus(),
    secrets=[modal.Secret.from_name(os.environ["MODAL_HF_SECRET"])] if os.getenv("MODAL_HF_SECRET") else [],
    volumes={"/models": model_volume},
    port=AGENT_PORT,
    min_containers=0,
    max_containers=1,
    target_concurrency=2,
    max_concurrency=4,
    scaledown_window=30,
    startup_timeout=900,
    # El proxy de Modal exige autenticación. No se publica vLLM ni una API abierta.
    unauthenticated=False,
)
class BibliotecaAgentServer:
    @modal.enter()
    def start(self) -> None:
        environment = os.environ.copy()
        environment["AGENT_VLLM_BASE_URL"] = f"http://127.0.0.1:{VLLM_PORT}/v1"
        environment["AGENT_VLLM_API_KEY"] = "local-loopback"

        self.vllm = subprocess.Popen(
            build_vllm_command(
                MODEL,
                api_key="local-loopback",
                port=VLLM_PORT,
                max_model_len=int(os.getenv("MODAL_MAX_MODEL_LEN", "8192")),
            ),
            env=environment,
        )
        _wait_for_http(
            f"http://127.0.0.1:{VLLM_PORT}/health",
            self.vllm,
            timeout=780,
        )

        self.agent = subprocess.Popen(
            [
                "python",
                "-m",
                "uvicorn",
                "biblioteca_agent.api:app",
                "--host",
                "0.0.0.0",
                "--port",
                str(AGENT_PORT),
                "--workers", "1",
            ],
            env=environment,
        )
        _wait_for_http(
            f"http://127.0.0.1:{AGENT_PORT}/health",
            self.agent,
            timeout=60,
        )

    @modal.exit()
    def stop(self) -> None:
        for process_name in ("agent", "vllm"):
            process = getattr(self, process_name, None)
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
