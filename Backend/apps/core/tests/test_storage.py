from io import BytesIO
from unittest.mock import MagicMock, patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from PIL import Image

from apps.core import storage


def create_png_bytes(size=(640, 480)):
    output = BytesIO()
    Image.new("RGB", size, color=(140, 20, 30)).save(output, format="PNG")
    return output.getvalue()


PNG_BYTES = create_png_bytes()
JPEG_BYTES = b"\xff\xd8\xff\xe0" + (b"\x00" * 32)


@override_settings(
    S3_ENDPOINT="http://rustfs:9000",
    S3_PUBLIC_ENDPOINT="http://localhost:9000",
    S3_BUCKET="imagenes",
    S3_REGION="us-east-1",
    S3_ACCESS_KEY="access",
    S3_SECRET_KEY="secret",
    S3_MAX_IMAGE_SIZE=1024 * 1024,
    S3_ALLOWED_IMAGE_CONTENT_TYPES=(
        "image/jpeg",
        "image/png",
        "image/gif",
        "image/webp",
    ),
)
class ImageStorageTests(SimpleTestCase):
    def test_upload_returns_permanent_public_url(self):
        file = SimpleUploadedFile(
            "logo.png",
            PNG_BYTES,
            content_type="image/png",
        )
        client = MagicMock()

        with patch(
            "apps.core.storage.get_s3_client",
            return_value=client,
        ):
            stored = storage.upload_image(file=file, folder="platforms")

        self.assertTrue(stored.key.startswith("platforms/"))
        self.assertTrue(stored.key.endswith(".png"))
        self.assertEqual(
            stored.url,
            f"http://localhost:9000/imagenes/{stored.key}",
        )
        self.assertNotIn("X-Amz-Expires", stored.url)
        self.assertNotIn("Signature", stored.url)

        self.assertEqual(client.put_object.call_count, 2)
        call = client.put_object.call_args_list[0].kwargs
        self.assertEqual(call["Bucket"], "imagenes")
        self.assertEqual(call["Key"], stored.key)
        self.assertEqual(call["ContentType"], "image/png")
        thumbnail_call = client.put_object.call_args_list[1].kwargs
        self.assertEqual(thumbnail_call["Key"], stored.thumbnail_key)
        self.assertEqual(thumbnail_call["ContentType"], "image/webp")
        thumbnail = Image.open(BytesIO(thumbnail_call["Body"]))
        self.assertLessEqual(max(thumbnail.size), 320)
        self.assertEqual(stored.thumbnail_url, storage.build_public_url(stored.thumbnail_key))

    def test_detects_real_format_instead_of_filename(self):
        file = SimpleUploadedFile(
            "not-really-an-image.txt",
            JPEG_BYTES,
            content_type="text/plain",
        )

        _, content_type, extension = storage.validate_uploaded_image(file)

        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(extension, ".jpg")

    def test_rejects_non_image_content(self):
        file = SimpleUploadedFile(
            "fake.png",
            b"this is not an image",
            content_type="image/png",
        )

        with self.assertRaises(storage.ImageStorageError):
            storage.validate_uploaded_image(file)

    def test_rejects_images_over_size_limit(self):
        file = SimpleUploadedFile(
            "large.png",
            PNG_BYTES + (b"\x00" * (1024 * 1024)),
            content_type="image/png",
        )

        with self.assertRaises(storage.ImageStorageError):
            storage.validate_uploaded_image(file)

    def test_external_urls_are_never_deleted(self):
        client = MagicMock()

        with patch(
            "apps.core.storage.get_s3_client",
            return_value=client,
        ):
            deleted = storage.delete_image_by_url(
                "https://example.org/platform.png"
            )

        self.assertFalse(deleted)
        client.delete_object.assert_not_called()

    def test_managed_urls_are_deleted(self):
        url = storage.build_public_url("platforms/image.png")
        client = MagicMock()

        with patch(
            "apps.core.storage.get_s3_client",
            return_value=client,
        ):
            deleted = storage.delete_image_by_url(url)

        self.assertTrue(deleted)
        client.delete_object.assert_called_once_with(
            Bucket="imagenes",
            Key="platforms/image.png",
        )
