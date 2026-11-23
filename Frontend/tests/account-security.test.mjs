import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import test from "node:test";

// Resolve the same source alias as Next.js without adding a test framework.
registerHooks({
  resolve(specifier, context, nextResolve) {
    if (specifier.startsWith("@/")) {
      return nextResolve(new URL(`../src/${specifier.slice(2)}.js`, import.meta.url).href, context);
    }
    return nextResolve(specifier, context);
  },
});
const { pendingAccountStep, createAccountsApi } = await import("../src/shared/services/apiClient.js");

const pending = {
  is_superadmin: false,
  superadmin_handoff_pending: true,
  must_change_password: true,
  mfa_enrollment_required: true,
  mfa_required: true,
  mfa_satisfied: false,
};

test("successor completes password and enrollment before entering the panel", () => {
  assert.equal(pendingAccountStep(pending), "password");
  assert.equal(pendingAccountStep({ ...pending, must_change_password: false }), "mfa-enroll");
  assert.equal(pendingAccountStep({
    ...pending, must_change_password: false, mfa_enrollment_required: false, mfa_satisfied: true,
  }), "handoff");
  assert.equal(pendingAccountStep({
    ...pending, is_superadmin: true, superadmin_handoff_pending: false,
    must_change_password: false, mfa_enrollment_required: false, mfa_satisfied: true,
  }), null);
});

test("pending successor cannot bypass the gate if mfa_required is absent or false", () => {
  assert.equal(pendingAccountStep({
    is_superadmin: false, superadmin_handoff_pending: true, mfa_required: false,
  }), "mfa-challenge");
});

test("superadmin must satisfy MFA on each login, including nested login responses", () => {
  assert.equal(pendingAccountStep({ user: { is_superadmin: true }, mfa_satisfied: false }), "mfa-challenge");
  assert.equal(pendingAccountStep({ user: { is_superadmin: true }, mfa_satisfied: true }), null);
  assert.equal(pendingAccountStep({ user: { force_password_change: true }, mfa_enrollment_required: true }), "password");
  assert.equal(pendingAccountStep({ is_superadmin: true, mfa_enrollment_required: true, mfa_satisfied: true }), "mfa-enroll");
});

test("ordinary administrative accounts keep their existing login flow", () => {
  assert.equal(pendingAccountStep({ is_superadmin: false, mfa_required: false }), null);
  assert.equal(pendingAccountStep({ must_change_password: true }), "password");
});

test("handoff cancellation uses DELETE and accepts an empty 204 response", async () => {
  let request;
  const api = createAccountsApi(async (...args) => {
    request = args;
    return { status: 204 };
  });
  assert.equal(await api.cancelSuperadminHandoff(), null);
  assert.deepEqual(request, ["superadmin/accounts/", "DELETE", {}]);
});

test("API errors retain status and field details for handoff feedback", async () => {
  for (const [status, data] of [
    [409, { email: ["Ya existe una cuenta con este correo."] }],
    [409, { detail: "Ya existe una transferencia superadmin pendiente." }],
    [404, { detail: "No hay una transferencia pendiente." }],
    [503, { detail: "No se pudo entregar el correo de invitación." }],
    [403, { code: "recent_authentication_required", detail: "Vuelve a iniciar sesión." }],
  ]) {
    const api = createAccountsApi(async () => ({ status, data }));
    await assert.rejects(api.cancelSuperadminHandoff(), (error) => {
      assert.equal(error.status, status);
      assert.deepEqual(error.data, data);
      assert.equal(error.recentAuthRequired, status === 403);
      return true;
    });
  }
});
