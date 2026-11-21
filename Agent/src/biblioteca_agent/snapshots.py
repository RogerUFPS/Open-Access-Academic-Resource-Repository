"""Snapshots inmutables y direccionados por hash, recibidos del backend privado."""
import hashlib
import json
import os
import tempfile

from .catalog import _validate_snapshot
from .config import PROJECT_ROOT


ROOT = PROJECT_ROOT / "data" / "catalogs"


def path_for(digest):
    return ROOT / f"{digest}.json"


def install(digest, snapshot):
    _validate_snapshot(snapshot)
    serialized = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    if len(serialized) > 50_000_000 or hashlib.sha256(serialized).hexdigest() != digest:
        raise ValueError("Hash o tamaño de catálogo inválido.")
    ROOT.mkdir(parents=True, exist_ok=True)
    target = path_for(digest)
    if not target.exists():
        descriptor, temporary = tempfile.mkstemp(dir=ROOT)
        try:
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(serialized)
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return target
