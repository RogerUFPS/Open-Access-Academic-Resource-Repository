"""Carga perfiles de modelo sin source/shell ni dependencia de python-dotenv."""
import os
from pathlib import Path

from deploy.model_config import load_deployment_model


def load_cloud_gpus():
    """Alternativas ordenadas; una sola GPU, sin fallback abierto/costoso."""
    raw = os.getenv("MODAL_GPU", "L4,A10,L40S")
    choices = list(dict.fromkeys(item.strip() for item in raw.split(",") if item.strip()))
    if not choices or any(item not in {"L4", "A10", "L40S"} for item in choices):
        raise ValueError("MODAL_GPU debe contener L4, A10 o L40S separados por comas.")
    return choices


def load_cloud_model(root: Path):
    # El worker remoto ya recibe el perfil completo dentro de su imagen.
    if os.getenv("MODEL_CHECKPOINT"):
        return load_deployment_model()
    path = (root / os.getenv("MODEL_ENV_FILE", "deploy/models/qwen.env")).resolve()
    if root.resolve() not in path.parents:
        raise ValueError("El perfil del modelo debe estar dentro de Agent.")
    values = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            raise ValueError("Perfil de modelo inválido.")
        values[key.strip()] = value.strip()
    return load_deployment_model({**values, **os.environ})
