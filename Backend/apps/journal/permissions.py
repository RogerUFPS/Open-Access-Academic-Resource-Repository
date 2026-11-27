from apps.account.permissions import ApplicationPermission, has_permission


class JournalLinkVerificationPermission(ApplicationPermission):
    """``POST /api/journals/{id}/check-links/`` exige el permiso de verificación
    de enlaces (``platforms.platforms.check_link``), el mismo que el resto de
    verificaciones y que define a los destinatarios de las alertas.

    Conserva las comprobaciones de sesión de ApplicationPermission: usuario
    autenticado, sin cambio de contraseña pendiente y MFA del superadmin.
    """

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.force_password_change:
            self.message = "Debes cambiar tu contraseña antes de continuar."
            return False
        if user.is_superadmin and not request.session.get("superadmin_mfa_satisfied"):
            self.message = "Debes completar la verificación MFA antes de continuar."
            return False
        return has_permission(user, "platforms", "platforms", "check_link")
