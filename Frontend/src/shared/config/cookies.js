// Única fuente de los nombres de las cookies de sesión y CSRF. Deben coincidir
// exactamente con SESSION_COOKIE_NAME y CSRF_COOKIE_NAME del backend. Los
// valores NEXT_PUBLIC_* se incorporan durante `next build`, por lo que también
// deben pasarse como argumentos de construcción del contenedor.
const COOKIE_NAME = /^[!#$%&'*+\-.^_`|~0-9A-Za-z]+$/;

function cookieName(value, fallback) {
  const name = value?.trim();
  return name && COOKIE_NAME.test(name) ? name : fallback;
}

export const SESSION_COOKIE_NAME = cookieName(process.env.NEXT_PUBLIC_SESSION_COOKIE_NAME, "sessionid");
export const CSRF_COOKIE_NAME = cookieName(process.env.NEXT_PUBLIC_CSRF_COOKIE_NAME, "csrftoken");

/** Las cookies `__Host-` sólo son aceptadas con Secure, Path=/ y sin Domain. */
export function requiresSecureCookie(name) {
  return name.startsWith("__Host-") || name.startsWith("__Secure-");
}
