"""Configuración por entorno y construcción segura del comando vLLM."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Mapping


@dataclass(frozen=True, slots=True)
class DeploymentModel:
    name: str
    aliases: tuple[str, ...]
    checkpoint: str
    served_model: str
    tool_call_parser: str
    quantization: str
    request_options_json: str


def load_deployment_model(environment: Mapping[str, str] | None = None) -> DeploymentModel:
    values = os.environ if environment is None else environment
    model = DeploymentModel(
        name=values.get("AGENT_MODEL_NAME", "qwen").strip(),
        aliases=tuple(
            item.strip()
            for item in values.get(
                "AGENT_MODEL_ALIASES", "qwen3:8b,biblioteca-qwen3-8b"
            ).split(",")
            if item.strip()
        ),
        checkpoint=values.get("MODEL_CHECKPOINT", "Qwen/Qwen3-8B-AWQ").strip(),
        served_model=values.get("VLLM_SERVED_MODEL", "biblioteca-qwen3-8b").strip(),
        tool_call_parser=values.get("VLLM_TOOL_CALL_PARSER", "hermes").strip(),
        quantization=values.get("VLLM_QUANTIZATION", "awq").strip(),
        request_options_json=values.get(
            "VLLM_REQUEST_OPTIONS_JSON", '{"chat_template_kwargs":{"enable_thinking":false}}'
        ).strip(),
    )
    if not all((model.name, model.checkpoint, model.served_model)):
        raise ValueError("AGENT_MODEL_NAME, MODEL_CHECKPOINT y VLLM_SERVED_MODEL son obligatorios.")
    try:
        request_options = json.loads(model.request_options_json or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("VLLM_REQUEST_OPTIONS_JSON no contiene JSON válido.") from exc
    if not isinstance(request_options, dict):
        raise ValueError("VLLM_REQUEST_OPTIONS_JSON debe ser un objeto JSON.")
    return model


def deployment_environment(model: DeploymentModel) -> dict[str, str]:
    """Propaga el perfil completo también al importar módulos en cloud."""
    return {
        "AGENT_MODEL_NAME": model.name,
        "AGENT_MODEL_ALIASES": ",".join(model.aliases),
        "MODEL_CHECKPOINT": model.checkpoint,
        "VLLM_SERVED_MODEL": model.served_model,
        "VLLM_TOOL_CALL_PARSER": model.tool_call_parser,
        "VLLM_QUANTIZATION": model.quantization,
        "VLLM_REQUEST_OPTIONS_JSON": model.request_options_json,
    }


def build_vllm_command(
    model: DeploymentModel,
    *,
    api_key: str | None = None,
    host: str = "127.0.0.1",
    port: int = 8000,
    max_model_len: int = 8192,
) -> list[str]:
    command = [
        "python",
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--host",
        host,
        "--port",
        str(port),
        "--model",
        model.checkpoint,
        "--served-model-name",
        model.served_model,
        "--dtype",
        "half",
        "--max-model-len",
        str(max_model_len),
        "--gpu-memory-utilization",
        os.getenv("VLLM_GPU_MEMORY_UTILIZATION", "0.90"),
        "--max-num-seqs",
        os.getenv("VLLM_MAX_NUM_SEQS", "8"),
        "--enforce-eager",
    ]
    if api_key:
        command.extend(["--api-key", api_key])
    if model.quantization:
        command.extend(["--quantization", model.quantization])
    if model.tool_call_parser:
        command.extend(["--enable-auto-tool-choice", "--tool-call-parser", model.tool_call_parser])
    return command
