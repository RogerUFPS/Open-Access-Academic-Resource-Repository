"""Provisiona un Proxy Token privado sin imprimir credenciales.

Ejecutar solo en el contenedor modal-cli, con Backend montado en /backend.
No forma parte de la imagen del agente ni de la API pública.
"""
import argparse
import json
import os
import tempfile
from pathlib import Path

import modal


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="/backend/.agent.env")
    parser.add_argument("--qwen-url")
    parser.add_argument("--glm-url")
    parser.add_argument("--llama-url")
    args = parser.parse_args()
    path = Path(args.output)
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            key, separator, value = line.partition("=")
            if separator and not key.startswith("#"):
                try:
                    values[key] = json.loads(value)
                except ValueError:
                    values[key] = value
    if not values.get("AGENT_MODAL_KEY") or not values.get("AGENT_MODAL_SECRET"):
        token = modal.Workspace.from_context().proxy_tokens.create(name="biblioteca-backend")
        values.update(AGENT_MODAL_KEY=token.token_id, AGENT_MODAL_SECRET=token.token_secret)
    for name in ("qwen", "glm", "llama"):
        url = getattr(args, f"{name}_url")
        if url:
            if not url.startswith("https://") or "\n" in url:
                raise ValueError("El endpoint Modal debe ser HTTPS.")
            values[f"AGENT_{name.upper()}_URL"] = url.rstrip("/")
    descriptor, temporary = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(descriptor, "w") as stream:
            for key, value in values.items():
                stream.write(f"{key}={json.dumps(value)}\n")
        os.replace(temporary, path)
        owner = path.parent.stat()
        os.chown(path, owner.st_uid, owner.st_gid)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    print("Configuración privada guardada. No se imprimieron claves.")


if __name__ == "__main__":
    main()
