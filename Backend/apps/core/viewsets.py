from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django.utils import timezone
from django.utils.cache import patch_cache_control
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.account.models import User

from .serializers import ImageUploadSerializer
from .storage import (
    ImageStorageError,
    delete_image,
    delete_image_by_url,
    upload_image,
)

SYSTEM_USER_CODE = 0


class PublicReadCacheMixin:
    cache_shared_public_responses = True

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        user = getattr(request, "user", None)
        has_authorization = bool(request.META.get("HTTP_AUTHORIZATION"))
        if (
            self.cache_shared_public_responses
            and request.method in {"GET", "HEAD"}
            and response.status_code == 200
            and not request.COOKIES
            and not has_authorization
            and not (user and user.is_authenticated)
        ):
            patch_cache_control(
                response,
                public=True,
                max_age=0,
                s_maxage=300,
            )
        return response


def get_acting_user(request):
    if request.user and request.user.is_authenticated:
        return request.user
    return User.all_objects.get(code=SYSTEM_USER_CODE)


class ResourceImageMixin:
    """
    Acciones compartidas para administrar la imagen de una ficha.

    La imagen es opcional y se publica como URL permanente en RustFS.
    Las URLs externas existentes (por ejemplo, las obtenidas por
    cosecha) nunca se eliminan del almacenamiento.
    """

    image_folder = ""

    def _upload_resource_image(self, request):
        instance = self.get_object()

        body = ImageUploadSerializer(data=request.data)
        body.is_valid(raise_exception=True)

        previous_url = instance.url_image
        previous_thumbnail_url = instance.url_image_thumbnail

        try:
            stored = upload_image(
                file=body.validated_data["image"],
                folder=self.image_folder,
            )
        except ImageStorageError as error:
            return Response(
                {"image": [error.message]},
                status=error.status_code,
            )

        try:
            instance.url_image = stored.url
            instance.url_image_thumbnail = stored.thumbnail_url
            instance.updated_by = get_acting_user(request)
            instance.updated_at = timezone.now()
            instance.save(
                update_fields=[
                    "url_image",
                    "url_image_thumbnail",
                    "updated_by",
                    "updated_at",
                ]
            )
        except Exception:
            delete_image(stored.key)
            delete_image(stored.thumbnail_key)
            raise

        if previous_url and previous_url != stored.url:
            delete_image_by_url(previous_url)
        if previous_thumbnail_url and previous_thumbnail_url != stored.thumbnail_url:
            delete_image_by_url(previous_thumbnail_url)

        return Response(
            self.get_serializer(instance).data,
            status=status.HTTP_200_OK,
        )

    def _delete_resource_image(self, request):
        instance = self.get_object()
        previous_url = instance.url_image
        previous_thumbnail_url = instance.url_image_thumbnail

        instance.url_image = None
        instance.url_image_thumbnail = None
        instance.updated_by = get_acting_user(request)
        instance.updated_at = timezone.now()
        instance.save(
            update_fields=[
                "url_image",
                "url_image_thumbnail",
                "updated_by",
                "updated_at",
            ]
        )

        if previous_url:
            delete_image_by_url(previous_url)
        if previous_thumbnail_url:
            delete_image_by_url(previous_thumbnail_url)

        return Response(
            self.get_serializer(instance).data,
            status=status.HTTP_200_OK,
        )


class DeleteSerializer(serializers.Serializer):
    delete_explanation = serializers.CharField(max_length=500, allow_blank=False)


class ArchivedNameMixin:
    archived_unique_fields = ()

    def to_internal_value(self, data):
        data = data.copy()
        if "name" in self.archived_unique_fields and isinstance(data.get("name"), str):
            data["name"] = data["name"].strip().lower()
        return super().to_internal_value(data)

    def validate(self, attrs):
        for field in self.archived_unique_fields:
            if field == "name" and field in attrs and isinstance(attrs[field], str):
                attrs[field] = attrs[field].strip().lower()
        attrs = super().validate(attrs)
        self._archived_instance = None
        filters = {
            field: attrs[field]
            for field in self.archived_unique_fields
            if field in attrs
        }
        if filters:
            active_duplicates = {
                field: self.Meta.model.all_objects.filter(
                    deleted_at__isnull=True,
                    **{f"{field}__iexact": value},
                ).exclude(pk=getattr(self.instance, "pk", None)).exists()
                for field, value in filters.items()
            }
            if any(active_duplicates.values()):
                raise serializers.ValidationError(
                    {
                        field: "Ya existe un registro activo con este valor."
                        for field, duplicate in active_duplicates.items()
                        if duplicate
                    }
                )
            self._archived_instance = self.Meta.model.all_objects.filter(
                deleted_at__isnull=False,
                **{
                    f"{field}__iexact": value
                    for field, value in filters.items()
                },
            ).first()
        return attrs

    def create(self, validated_data):
        archived = getattr(self, "_archived_instance", None)
        if archived is None:
            return super().create(validated_data)

        acting_user = validated_data.pop("created_by", None)
        for field, value in validated_data.items():
            setattr(archived, field, value)
        archived.restore()
        archived.updated_by = acting_user
        archived.updated_at = timezone.now()
        archived.save(update_fields=[
            *validated_data.keys(),
            "deleted_by",
            "deleted_at",
            "delete_explanation",
            "updated_by",
            "updated_at",
        ])
        return archived


class AuditableViewSet(viewsets.ModelViewSet):
    def _has_business_relations(self, instance):
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        for relation in instance._meta.related_objects:
            if relation.related_model is user_model:
                continue
            related_queryset = relation.related_model._base_manager.filter(
                **{relation.field.name: instance}
            )
            if related_queryset.exists():
                return True
        return False

    @action(detail=False, methods=["get"], url_path="archived")
    def archived(self, request):
        queryset = self.queryset.model.all_objects.filter(deleted_at__isnull=False)
        queryset = self.filter_queryset(queryset)
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    def perform_create(self, serializer):
        serializer.save(created_by=get_acting_user(self.request))

    def perform_update(self, serializer):
        serializer.save(
            updated_by=get_acting_user(self.request),
            updated_at=timezone.now(),
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        has_business_relations = self._has_business_relations(instance)
        if has_business_relations:
            body = DeleteSerializer(data=request.data)
            body.is_valid(raise_exception=True)
        acting_user = get_acting_user(request)
        explanation = (
            body.validated_data["delete_explanation"]
            if has_business_relations
            else None
        )
        if not has_business_relations:
            try:
                instance.delete()
                return Response(status=status.HTTP_204_NO_CONTENT)
            except (IntegrityError, ProtectedError):
                pass
        try:
            instance.soft_delete(
                user=acting_user,
                explanation=explanation,
            )
        except ValueError as error:
            return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(
            {
                "detail": (
                    "El registro fue desactivado mediante borrado lógico porque "
                    "otros elementos dependen de él."
                ),
                "permanent": False,
            },
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="restore")
    def restore(self, request, pk=None):
        model = self.queryset.model
        try:
            instance = model.all_objects.get(pk=pk, deleted_at__isnull=False)
        except (model.DoesNotExist, ValueError):
            return Response(
                {"detail": "No existe un registro eliminado con ese id."},
                status=status.HTTP_404_NOT_FOUND,
            )
        instance.restore()
        instance.updated_by = get_acting_user(request)
        instance.updated_at = timezone.now()
        instance.save(update_fields=["updated_by", "updated_at"])
        return Response(self.get_serializer(instance).data)
