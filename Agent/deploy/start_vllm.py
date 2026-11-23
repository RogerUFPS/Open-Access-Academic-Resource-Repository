"""Entrypoint de Compose sin interpolación de comandos por shell."""

from __future__ import annotations

import os

from model_config import build_vllm_command, load_deployment_model


model = load_deployment_model()
command = build_vllm_command(
    model,
    api_key=os.getenv("AGENT_VLLM_API_KEY", "local-compose"),
    host="0.0.0.0",
    port=8000,
    max_model_len=int(os.getenv("VLLM_MAX_MODEL_LEN", "8192")),
)
os.execvp(command[0], command)
