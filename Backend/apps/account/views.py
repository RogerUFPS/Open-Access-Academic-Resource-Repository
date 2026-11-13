import secrets
from html import escape

from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.sessions.backends.db import SessionStore
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from django.utils.decorators import method_decorator
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .email import EmailDeliveryError, login_link_html, send_email
from .models import AccessPreset, SessionTermination, User
from .permissions import PERMISSION_MATRIX
from .security import (
    audit_superadmin,
    encrypt_totp_secret,
    enrollment_uri,
    new_totp_secret,
    verify_totp,
)
from apps.core.utils.crypto import decrypt_api_key
from .serializers import (
    AccessPresetSerializer,
    AssignPresetsSerializer,
    ChangePasswordSerializer,
    ForgotPasswordSerializer,
    InviteSerializer,
    LoginSerializer,
    ProfileSerializer,
    RegistrationSerializer,
    UserAdminUpdateSerializer,
    UserPermissionsSerializer,
    UserSerializer,
)


def temporary_password():
    return secrets.token_urlsafe(18)


def invalidate_current_session(user, reason):
    session_key = user.session_key
    if session_key:
        SessionTermination.record(user, session_key, reason=reason)
        SessionStore(session_key=session_key).delete()
        user.session_key = None


class CsrfView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(ensure_csrf_cookie)
    def get(self, request):
        return Response({"detail": "Token CSRF disponible en la cookie csrftoken."})


class LoginView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(csrf_protect)
    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip().lower()
        user = authenticate(
            request,
            email=email,
            password=serializer.validated_data["password"],
        )
        if user is None:
            candidate = User.objects.filter(email__iexact=email, is_superadmin=True).first()
            if candidate:
                audit_superadmin("login_failed", target=candidate, details={"stage": "password"})
            return Response(
                {"detail": "Correo o contraseña incorrectos."},
                status=status.HTTP_401_UNAUTHORIZED,
            )

        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=user.pk)
            previous_session_terminated = bool(
                user.session_key and user.session_key != request.session.session_key
            )
            if previous_session_terminated:
                SessionTermination.record(user, user.session_key)
                SessionStore(session_key=user.session_key).delete()
            login(request, user)
            if user.is_superadmin:
                request.session["superadmin_mfa_satisfied"] = False
                request.session["superadmin_mfa_enrollment_required"] = not user.mfa_enabled
                audit_superadmin("login_password_accepted", actor=user, target=user)
            else:
                request.session.pop("superadmin_mfa_satisfied", None)
            request.session.save()
            user.session_key = request.session.session_key
            user.save(update_fields=["session_key"])

        return Response({
            "user": {**UserSerializer(user).data, "is_superadmin": user.is_superadmin,
                     "mfa_enabled": user.mfa_enabled},
            "must_change_password": user.force_password_change,
            "is_superadmin": user.is_superadmin,
            "mfa_required": user.is_superadmin,
            "mfa_enrollment_required": bool(user.is_superadmin and not user.mfa_enabled),
            "mfa_satisfied": bool(not user.is_superadmin or request.session.get("superadmin_mfa_satisfied")),
            "previous_session_terminated": previous_session_terminated,
        })


class MFAChallengeView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        code = str(request.data.get("code", ""))
        user = request.user
        if not user.is_superadmin or not user.is_active or not user.mfa_enabled:
            if user.is_superadmin:
                audit_superadmin("mfa_challenge_failed", target=user)
            return Response({"detail": "No se pudo verificar el código."}, status=400)
        if not verify_totp(user, code):
            audit_superadmin("mfa_challenge_failed", actor=user, target=user)
            return Response({"detail": "Código MFA no válido."}, status=400)
        request.session["superadmin_mfa_satisfied"] = True
        request.session.pop("superadmin_mfa_enrollment_required", None)
        audit_superadmin("mfa_challenge_succeeded", actor=user, target=user)
        audit_superadmin("login_succeeded", actor=user, target=user)
        return Response({"mfa_satisfied": True})


class MFAEnrollmentView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if not user.is_superadmin or not user.is_active or user.force_password_change:
            return Response({"detail": "Cambia la contraseña antes de configurar MFA."}, status=403)
        if user.mfa_enabled:
            return Response({"detail": "MFA ya está configurado."}, status=409)
        secret = decrypt_api_key(user.mfa_secret) if user.mfa_secret else ""
        if not secret:
            secret = new_totp_secret()
            user.mfa_secret = encrypt_totp_secret(secret)
            user.save(update_fields=["mfa_secret"])
            audit_superadmin("mfa_enrollment_started", actor=user, target=user)
        return Response({"secret": secret, "otpauth_uri": enrollment_uri(user, secret)})


class MFAEnrollmentConfirmView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        if (not user.is_superadmin or not user.is_active or user.force_password_change
                or user.mfa_enabled):
            return Response({"detail": "No se puede completar la inscripción MFA."}, status=403)
        if not verify_totp(user, str(request.data.get("code", ""))):
            audit_superadmin("mfa_enrollment_failed", actor=user, target=user)
            return Response({"detail": "Código MFA no válido."}, status=400)
        user.mfa_enabled = True
        user.save(update_fields=["mfa_enabled"])
        request.session["superadmin_mfa_satisfied"] = True
        request.session.pop("superadmin_mfa_enrollment_required", None)
        audit_superadmin("mfa_enrollment_completed", actor=user, target=user)
        audit_superadmin("login_succeeded", actor=user, target=user)
        return Response({"mfa_enabled": True, "mfa_satisfied": True})


class SuperadminAccountsView(APIView):
    """Lifecycle actions for the authenticated superadmin only."""

    def post(self, request):
        email = str(request.data.get("email", "")).strip().lower()
        try:
            from django.core.validators import validate_email
            validate_email(email)
        except Exception:
            return Response({"email": ["Introduce un correo válido."]}, status=400)
        if User.all_objects.filter(email__iexact=email).exists():
            return Response({"email": ["Ya existe una cuenta con este correo."]}, status=409)
        password = temporary_password()
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email=email,
                    password=password,
                    is_superadmin=True,
                    force_password_change=True,
                    created_by=request.user,
                )
                try:
                    send_email(email, "Nueva cuenta superadmin",
                        "<p>Tu contraseña temporal es:</p>"
                        f"<p><strong>{escape(password)}</strong></p>"
                        "<p>Debes cambiarla y configurar MFA al iniciar sesión.</p>"
                        f"{login_link_html()}")
                except EmailDeliveryError:
                    transaction.set_rollback(True)
                    return Response({"detail": "No se pudo entregar el correo de invitación."}, status=503)
                audit_superadmin("superadmin_created", actor=request.user, target=user)
        except IntegrityError:
            return Response({"email": ["Ya existe una cuenta con este correo."]}, status=409)
        return Response({"id": user.pk, "email": user.email,
                         "force_password_change": True, "mfa_enrollment_required": True}, status=201)


class DeactivateSuperadminView(APIView):
    @transaction.atomic
    def post(self, request):
        actor = User.objects.select_for_update().filter(pk=request.user.pk,
                                                        is_active=True,
                                                        is_superadmin=True).first()
        if actor is None:
            return Response({"detail": "La cuenta ya no está activa."}, status=403)
        replacement_ready = User.objects.filter(is_superadmin=True, is_active=True,
            mfa_enabled=True, force_password_change=False).exclude(pk=actor.pk).exists()
        if not replacement_ready:
            return Response({"detail": "Se requiere otra cuenta superadmin activa y con MFA configurado."}, status=409)
        invalidate_current_session(actor, SessionTermination.Reason.ACCOUNT_DISABLED)
        actor.is_active = False
        actor.save(update_fields=["is_active", "session_key"])
        audit_superadmin("superadmin_deactivated", actor=actor, target=actor)
        logout(request)
        return Response({"detail": "Cuenta desactivada."})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        if request.user.is_superadmin:
            audit_superadmin("logout", actor=request.user, target=request.user)
        if request.user.session_key == request.session.session_key:
            request.user.session_key = None
            request.user.save(update_fields=["session_key"])
        logout(request)
        return Response({"detail": "Sesión cerrada."})


class RegisterView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(csrf_protect)
    def post(self, request):
        serializer = RegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.create_user(**serializer.validated_data)
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        return Response({**UserSerializer(user).data,
                         "is_superadmin": user.is_superadmin,
                         "mfa_enabled": user.mfa_enabled,
                         "mfa_required": user.is_superadmin,
                         "mfa_satisfied": bool(not user.is_superadmin or request.session.get("superadmin_mfa_satisfied")),
                         "mfa_enrollment_required": bool(user.is_superadmin and not user.mfa_enabled),
                         "must_change_password": user.force_password_change})

    def patch(self, request):
        if request.user.force_password_change:
            return Response(
                {"detail": "Debes cambiar tu contraseña antes de continuar."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if request.user.is_superadmin and "email" in request.data:
            return Response(
                {"email": ["El correo de superadmin no se puede cambiar; crea una nueva cuenta y desactiva esta."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = ProfileSerializer(
            request.user,
            data=request.data,
            partial=True,
        )
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user, updated_at=timezone.now())
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        if not request.user.check_password(serializer.validated_data["current_password"]):
            return Response(
                {"current_password": ["La contraseña actual no es correcta."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        request.user.set_password(serializer.validated_data["new_password"])
        request.user.force_password_change = False
        request.user.updated_by = request.user
        request.user.updated_at = timezone.now()
        request.user.save()
        update_session_auth_hash(request, request.user)
        request.user.session_key = request.session.session_key
        request.user.save(update_fields=["session_key"])
        if request.user.is_superadmin:
            audit_superadmin("password_changed", actor=request.user, target=request.user)
        return Response({"detail": "La contraseña se cambió correctamente."})


class ForgotPasswordView(APIView):
    permission_classes = [AllowAny]

    @method_decorator(csrf_protect)
    def post(self, request):
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        email = serializer.validated_data["email"].strip()
        # Superadmin recovery deliberately queries only current, active accounts.
        user = User.objects.filter(email__iexact=email, is_superadmin=True, is_active=True).first()
        if user is None:
            user = User.objects.filter(email__iexact=email, is_superadmin=False,
                                       is_active=True).first()
        if user is None:
            return Response({
                "detail": "Si el correo está registrado, recibirás una contraseña provisional."
            })

        password = temporary_password()
        try:
            send_email(
                user.email,
                "Recuperación de contraseña",
                (
                    "<p>Tu contraseña provisional es:</p>"
                    f"<p><strong>{escape(password)}</strong></p>"
                    "<p>Inicia sesión y cámbiala antes de continuar.</p>"
                    f"{login_link_html()}"
                ),
            )
        except EmailDeliveryError:
            return Response({"detail": "Si el correo está registrado, recibirás una contraseña provisional."})
        invalidate_current_session(
            user,
            reason=SessionTermination.Reason.CREDENTIALS_RESET,
        )
        user.set_password(password)
        user.force_password_change = True
        user.save(update_fields=["password", "force_password_change", "session_key"])
        if user.is_superadmin:
            audit_superadmin("password_reset", target=user)
        return Response({
            "detail": "Si el correo está registrado, recibirás una contraseña provisional."
        })


class UsersView(APIView):
    def get(self, request):
        return Response(UserSerializer(User.objects.order_by("id"), many=True).data)


class ArchivedUsersView(APIView):
    def get(self, request):
        users = User.all_objects.filter(
            deleted_at__isnull=False,
        ).order_by("id")
        return Response(UserSerializer(users, many=True).data)


class UserDetailView(APIView):
    def get_object(self, pk):
        return User.all_objects.filter(pk=pk, deleted_at__isnull=True).first()

    def get(self, request, pk):
        user = self.get_object(pk)
        if user is None:
            return Response({"detail": "Cuenta no encontrada."}, status=404)
        return Response(UserSerializer(user).data)

    def patch(self, request, pk):
        user = self.get_object(pk)
        if user is None:
            return Response({"detail": "Cuenta no encontrada."}, status=404)
        if user.is_superadmin:
            return Response(
                {"detail": "No se puede modificar la cuenta superadmin desde este endpoint."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = UserAdminUpdateSerializer(user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("is_active") is False:
            invalidate_current_session(
                user,
                reason=SessionTermination.Reason.ACCOUNT_DISABLED,
            )
        serializer.save(updated_by=request.user, updated_at=timezone.now())
        return Response(UserSerializer(user).data)

    def delete(self, request, pk):
        user = self.get_object(pk)
        if user is None or user.deleted_at is not None:
            return Response({"detail": "Cuenta no encontrada."}, status=404)
        if user.is_superadmin:
            return Response(
                {"detail": "No se puede desactivar la cuenta superadmin."},
                status=status.HTTP_403_FORBIDDEN,
            )
        invalidate_current_session(
            user,
            reason=SessionTermination.Reason.ACCOUNT_DISABLED,
        )
        user.is_active = False
        user.soft_delete(user=request.user, explanation="Cuenta desactivada por administración")
        user.save(update_fields=["is_active", "session_key"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class UserRestoreView(APIView):
    @transaction.atomic
    def post(self, request, pk):
        user = User.all_objects.select_for_update().filter(pk=pk).first()
        if user is None:
            return Response({"detail": "Cuenta no encontrada."}, status=404)
        if user.is_superadmin:
            return Response(
                {"detail": "No se puede restaurar la cuenta superadmin desde este endpoint."},
                status=status.HTTP_403_FORBIDDEN,
            )
        if user.deleted_at is None and user.is_active:
            return Response(
                {"detail": "La cuenta ya está activa."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        user.restore()
        user.is_active = True
        user.updated_by = request.user
        user.updated_at = timezone.now()
        user.session_key = None
        user.save(update_fields=[
            "is_active",
            "deleted_by",
            "deleted_at",
            "delete_explanation",
            "updated_by",
            "updated_at",
            "session_key",
        ])
        return Response(UserSerializer(user).data)


class InviteView(APIView):
    def post(self, request):
        serializer = InviteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        password = temporary_password()
        values = serializer.validated_data
        with transaction.atomic():
            user = User.objects.create_user(
                email=values["email"],
                password=password,
                full_name=values.get("full_name", ""),
                collegue_code=values.get("collegue_code", ""),
                force_password_change=True,
                created_by=request.user,
            )
            try:
                send_email(
                    user.email,
                    "Invitación al sistema de revistas",
                    (
                        f"<p>Tu correo de acceso es: {escape(user.email)}</p>"
                        "<p>Tu contraseña provisional es:</p>"
                        f"<p><strong>{escape(password)}</strong></p>"
                        "<p>Inicia sesión y cámbiala antes de continuar.</p>"
                        f"{login_link_html()}"
                    ),
                )
            except EmailDeliveryError as error:
                transaction.set_rollback(True)
                return Response(
                    {"detail": str(error)},
                    status=status.HTTP_503_SERVICE_UNAVAILABLE,
                )
        return Response(UserSerializer(user).data, status=status.HTTP_201_CREATED)


class UserPermissionsView(APIView):
    def put(self, request, pk):
        user = User.all_objects.filter(pk=pk).first()
        if user is None or user.deleted_at is not None:
            return Response({"detail": "Cuenta no encontrada."}, status=404)
        if user.is_superadmin:
            return Response(
                {"detail": "Los permisos del superadmin no se pueden modificar."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = UserPermissionsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user.permissions = serializer.validated_data["permissions"]
        user.updated_by = request.user
        user.updated_at = timezone.now()
        user.save(update_fields=["permissions", "updated_by", "updated_at"])
        return Response(UserSerializer(user).data)


class UserPresetsView(APIView):
    def put(self, request, pk):
        user = User.all_objects.filter(pk=pk).first()
        if user is None or user.deleted_at is not None:
            return Response({"detail": "Cuenta no encontrada."}, status=404)
        if user.is_superadmin:
            return Response(
                {"detail": "No se pueden asignar presets al superadmin."},
                status=status.HTTP_403_FORBIDDEN,
            )
        serializer = AssignPresetsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user.presets.set(serializer.validated_data["preset_ids"])
        user.updated_by = request.user
        user.updated_at = timezone.now()
        user.save(update_fields=["updated_by", "updated_at"])
        return Response(UserSerializer(user).data)


class PresetsView(APIView):
    def get(self, request):
        return Response(AccessPresetSerializer(AccessPreset.objects.all(), many=True).data)

    def post(self, request):
        serializer = AccessPresetSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(created_by=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class PresetDetailView(APIView):
    def get_object(self, pk):
        return AccessPreset.objects.filter(pk=pk).first()

    def get(self, request, pk):
        preset = self.get_object(pk)
        if preset is None:
            return Response({"detail": "Preset no encontrado."}, status=404)
        return Response(AccessPresetSerializer(preset).data)

    def patch(self, request, pk):
        preset = self.get_object(pk)
        if preset is None:
            return Response({"detail": "Preset no encontrado."}, status=404)
        serializer = AccessPresetSerializer(preset, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save(updated_by=request.user, updated_at=timezone.now())
        return Response(serializer.data)

    def delete(self, request, pk):
        preset = self.get_object(pk)
        if preset is None:
            return Response({"detail": "Preset no encontrado."}, status=404)
        preset.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PermissionsView(APIView):
    def get(self, request):
        return Response({
            app: {
                resource: list(actions)
                for resource, actions in resources.items()
            }
            for app, resources in PERMISSION_MATRIX.items()
        })
