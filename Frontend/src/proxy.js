import { NextResponse } from "next/server";

// Orígenes externos estrictamente necesarios: la API pública se consulta desde
// el navegador con NEXT_PUBLIC_API_URL; el panel usa los rewrites same-origin.
function origin(value) {
  try {
    return value ? new URL(value).origin : null;
  } catch {
    return null;
  }
}

function extraSources(value) {
  return (value ?? "").split(/\s+/).map(origin).filter(Boolean);
}

const API_ORIGIN = origin(process.env.NEXT_PUBLIC_API_URL);

function contentSecurityPolicy(nonce) {
  const isDev = process.env.NODE_ENV === "development";
  const secureDeployment = process.env.SECURE_DEPLOYMENT === "1";
  const connect = ["'self'", API_ORIGIN, ...extraSources(process.env.CSP_CONNECT_SRC)];
  // Los logos de recursos provienen de sitios externos arbitrarios por HTTPS.
  const images = ["'self'", "data:", "blob:", "https:", API_ORIGIN, ...extraSources(process.env.CSP_IMG_SRC)];
  if (isDev) {
    connect.push("ws:");
    images.push("http:");
  }
  const directives = [
    "default-src 'self'",
    `script-src 'self' 'nonce-${nonce}' 'strict-dynamic'${isDev ? " 'unsafe-eval'" : ""}`,
    // Estilos: Next.js, Radix y React (atributos style) los generan en línea.
    // La restricción estricta aplica a los scripts.
    "style-src 'self' 'unsafe-inline'",
    `img-src ${[...new Set(images.filter(Boolean))].join(" ")}`,
    "font-src 'self' data:",
    `connect-src ${[...new Set(connect.filter(Boolean))].join(" ")}`,
    "object-src 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
    "manifest-src 'self'",
    "worker-src 'self' blob:",
  ];
  if (secureDeployment) directives.push("upgrade-insecure-requests");
  if (process.env.CSP_REPORT_URI) directives.push(`report-uri ${process.env.CSP_REPORT_URI}`);
  return directives.join("; ");
}

export function proxy(request) {
  const nonce = Buffer.from(crypto.randomUUID()).toString("base64");
  const csp = contentSecurityPolicy(nonce);

  // Next.js extrae el nonce de este encabezado de la solicitud y lo aplica a
  // sus scripts durante el renderizado dinámico.
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-nonce", nonce);
  requestHeaders.set("Content-Security-Policy", csp);

  const response = NextResponse.next({ request: { headers: requestHeaders } });
  // CSP_REPORT_ONLY=1 permite validar la política en un entorno de prueba.
  response.headers.set(
    process.env.CSP_REPORT_ONLY === "1" ? "Content-Security-Policy-Report-Only" : "Content-Security-Policy",
    csp,
  );
  // HSTS sólo cuando el despliegue es HTTPS de extremo a extremo.
  if (process.env.SECURE_DEPLOYMENT === "1") {
    response.headers.set("Strict-Transport-Security", "max-age=63072000");
  }
  return response;
}

export const config = {
  matcher: [
    {
      // Sólo documentos HTML: se excluyen la API (rewrites), los recursos
      // estáticos y las prefetch de next/link.
      source: "/((?!api|_next/static|_next/image|favicon.ico|brand/|.*\\.(?:png|jpg|jpeg|gif|svg|ico|webp|txt|xml)$).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
