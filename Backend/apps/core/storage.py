from __future__ import annotations

import logging
import uuid
import warnings
from dataclasses import dataclass
from io import BytesIO
from urllib.parse import quote, unquote, urlsplit

import boto3
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from django.conf import settings
from PIL import Image, ImageOps, UnidentifiedImageError

logger = logging.getLogger(__name__)


DEFAULT_MAX_IMAGE_SIZE = 5 * 1024 * 1024
DEFAULT_ALLOWED_IMAGE_CONTENT_TYPES = (
    "image/jpeg",
    "image/png",
    "image/gif",
    "image/webp",
)

IMAGE_FORMATS = {
    "jpeg": ("image/jpeg", ".jpg"),
    "png": ("image/png", ".png"),
    "gif": ("image/gif", ".gif"),
    "webp": ("image/webp", ".webp"),
}


class ImageStorageError(Exception):
    """Error controlado del servicio de almacenamiento de imágenes."""

    def __init__(self, message: str, *, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


@dataclass(frozen=True)
class StoredImage:
    key: str
    url: str
    content_type: str
    size: int
    thumbnail_key: str | None = None
    thumbnail_url: str | None = None


def _setting(name: str, default=None):
    return getattr(settings, name, default)


def _bucket_name() -> str:
    bucket = (_setting("S3_BUCKET", "") or "").strip()
    if not bucket:
        raise ImageStorageError(
            "El bucket de imágenes no está configurado.",
            status_code=503,
        )
    return bucket


def _public_base_url() -> str:
    base_url = (
        _setting("S3_PUBLIC_ENDPOINT")
        or _setting("S3_ENDPOINT")
        or ""
    ).strip()
    if not base_url:
        raise ImageStorageError(
            "El servicio de imágenes no está configurado.",
            status_code=503,
        )
    return base_url.rstrip("/")


def _max_image_size() -> int:
    value = _setting("S3_MAX_IMAGE_SIZE", DEFAULT_MAX_IMAGE_SIZE)
    try:
        return max(1, int(value))
    except (TypeError, ValueError):
        return DEFAULT_MAX_IMAGE_SIZE


def _allowed_content_types() -> set[str]:
    configured = _setting(
        "S3_ALLOWED_IMAGE_CONTENT_TYPES",
        DEFAULT_ALLOWED_IMAGE_CONTENT_TYPES,
    )
    if isinstance(configured, str):
        configured = tuple(
            item.strip()
            for item in configured.split(",")
            if item.strip()
        )
    return set(configured or DEFAULT_ALLOWED_IMAGE_CONTENT_TYPES)


def detect_image_format(header: bytes) -> str | None:
    """Detecta el formato de imagen a partir de sus primeros bytes."""
    if header.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if (
        len(header) >= 12
        and header[:4] == b"RIFF"
        and header[8:12] == b"WEBP"
    ):
        return "webp"
    return None


def validate_uploaded_image(file) -> tuple[str, str, str]:
    """
    Valida el archivo y devuelve ``(formato, content_type, extensión)``.

    La validación se basa en la firma binaria real del archivo, no en el
    nombre ni en el ``Content-Type`` enviado por el cliente.
    """
    size = getattr(file, "size", None)
    if not size:
        raise ImageStorageError("El archivo de imagen está vacío.")

    max_size = _max_image_size()
    if size > max_size:
        max_mb = max_size / (1024 * 1024)
        raise ImageStorageError(
            f"La imagen supera el tamaño máximo permitido ({max_mb:g} MB)."
        )

    header = file.read(16)
    try:
        file.seek(0)
    except (AttributeError, OSError):
        pass

    image_format = detect_image_format(header)
    if image_format is None:
        raise ImageStorageError(
            "El archivo no es una imagen válida. "
            "Formatos admitidos: JPEG, PNG, GIF y WebP."
        )

    content_type, extension = IMAGE_FORMATS[image_format]
    if content_type not in _allowed_content_types():
        raise ImageStorageError(
            f"El formato {image_format.upper()} no está permitido."
        )

    return image_format, content_type, extension


def _create_thumbnail(file) -> bytes:
    file.seek(0)
    output = BytesIO()
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(file) as image:
                image.seek(0)
                thumbnail = ImageOps.exif_transpose(image)
                thumbnail.thumbnail((320, 320), Image.Resampling.LANCZOS)
                if thumbnail.mode not in {"RGB", "RGBA"}:
                    thumbnail = thumbnail.convert(
                        "RGBA" if "transparency" in thumbnail.info else "RGB"
                    )
                thumbnail.save(output, format="WEBP", quality=82, method=4)
    except (
        Image.DecompressionBombError,
        Image.DecompressionBombWarning,
        UnidentifiedImageError,
        OSError,
    ) as error:
        raise ImageStorageError(
            "No se pudo procesar la imagen para generar su miniatura."
        ) from error
    finally:
        file.seek(0)
    return output.getvalue()


def get_s3_client():
    """Crea un cliente S3 bajo demanda usando la configuración de RustFS."""
    endpoint_url = (_setting("S3_ENDPOINT", "") or "").strip()
    access_key = (
        _setting("S3_ACCESS_KEY", "")
        or _setting("RUSTFS_ACCESS_KEY", "")
    )
    secret_key = (
        _setting("S3_SECRET_KEY", "")
        or _setting("RUSTFS_SECRET_KEY", "")
    )

    if not endpoint_url or not access_key or not secret_key:
        raise ImageStorageError(
            "El servicio de almacenamiento de imágenes no está configurado.",
            status_code=503,
        )

    return boto3.session.Session().client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
        region_name=_setting("S3_REGION", "us-east-1"),
        config=Config(
            signature_version="s3v4",
            s3={"addressing_style": "path"},
            connect_timeout=5,
            read_timeout=30,
            retries={"max_attempts": 3, "mode": "standard"},
        ),
    )


def build_public_url(key: str) -> str:
    """
    Construye una URL pública permanente.

    No se usan URLs prefirmadas: el bucket ``imagenes`` de RustFS se
    configura con lectura anónima para que las imágenes no expiren.
    """
    bucket = _bucket_name()
    return (
        f"{_public_base_url()}/"
        f"{quote(bucket, safe='')}/"
        f"{quote(key.lstrip('/'), safe='/')}"
    )


def upload_image(*, file, folder: str) -> StoredImage:
    """Sube una imagen a RustFS y devuelve su URL pública permanente."""
    bucket = _bucket_name()
    _, content_type, extension = validate_uploaded_image(file)
    thumbnail = _create_thumbnail(file)

    normalized_folder = folder.strip("/")
    stem = uuid.uuid4().hex
    key = (
        f"{normalized_folder}/{stem}{extension}"
        if normalized_folder
        else f"{stem}{extension}"
    )
    thumbnail_key = (
        f"{normalized_folder}/{stem}.thumbnail.webp"
        if normalized_folder
        else f"{stem}.thumbnail.webp"
    )

    client = get_s3_client()
    original_uploaded = False
    try:
        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=file,
            ContentType=content_type,
            CacheControl="public, max-age=31536000, immutable",
        )
        original_uploaded = True
        client.put_object(
            Bucket=bucket,
            Key=thumbnail_key,
            Body=thumbnail,
            ContentType="image/webp",
            CacheControl="public, max-age=31536000, immutable",
        )
    except ImageStorageError:
        raise
    except (BotoCoreError, ClientError) as error:
        if original_uploaded:
            for uploaded_key in (key, thumbnail_key):
                try:
                    client.delete_object(Bucket=bucket, Key=uploaded_key)
                except (BotoCoreError, ClientError):
                    logger.warning(
                        "No se pudo limpiar una imagen tras fallar la miniatura: key=%s",
                        uploaded_key,
                        exc_info=True,
                    )
        logger.exception("No se pudo subir la imagen a RustFS: key=%s", key)
        raise ImageStorageError(
            "No se pudo almacenar la imagen. Intente nuevamente.",
            status_code=503,
        ) from error

    return StoredImage(
        key=key,
        url=build_public_url(key),
        content_type=content_type,
        size=getattr(file, "size", 0) or 0,
        thumbnail_key=thumbnail_key,
        thumbnail_url=build_public_url(thumbnail_key),
    )


def key_from_public_url(url: str | None) -> str | None:
    """
    Extrae la clave S3 de una URL pública generada por este servicio.

    Devuelve ``None`` para URLs externas (por ejemplo, imágenes obtenidas
    durante la cosecha), de modo que nunca se eliminen objetos ajenos.
    """
    if not url:
        return None

    try:
        base_url = _public_base_url()
        bucket = _bucket_name()
    except ImageStorageError:
        return None

    base = urlsplit(base_url)
    parsed = urlsplit(url)
    if (parsed.scheme, parsed.netloc) != (base.scheme, base.netloc):
        return None

    prefix = f"{base.path.rstrip('/')}/{bucket}/"
    if not parsed.path.startswith(prefix):
        return None

    key = unquote(parsed.path[len(prefix):])
    return key or None


def delete_image(key: str | None) -> bool:
    """Elimina una imagen de RustFS. Es una operación de mejor esfuerzo."""
    if not key:
        return False

    try:
        get_s3_client().delete_object(
            Bucket=_bucket_name(),
            Key=key,
        )
    except (ImageStorageError, BotoCoreError, ClientError):
        logger.warning(
            "No se pudo eliminar la imagen de RustFS: key=%s",
            key,
            exc_info=True,
        )
        return False
    return True


def delete_image_by_url(url: str | None) -> bool:
    """Elimina únicamente imágenes administradas por este backend."""
    return delete_image(key_from_public_url(url))
