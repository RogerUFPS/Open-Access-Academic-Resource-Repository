/** @type {import('next').NextConfig} */
const nextConfig = {
  output: "standalone",
  /* config options here */
  reactCompiler: true,
  // Server Function arguments include passwords during authentication.
  logging: { serverFunctions: false },
  // Django's API endpoints require their trailing slash, including POSTs.
  skipTrailingSlashRedirect: true,
  poweredByHeader: false,
  experimental: {
    // Las páginas del panel son cascarones de cliente: su respuesta del
    // servidor no trae datos, así que se puede reutilizar en el navegador y
    // volver a una pestaña ya visitada sin otro viaje. Los datos se revalidan
    // aparte (src/shared/query).
    staleTimes: { dynamic: 300, static: 300 },
  },
  async headers() {
    // La CSP con nonce y HSTS se aplican por petición en src/proxy.js.
    return [{
      source: "/:path*",
      headers: [
        { key: "X-Content-Type-Options", value: "nosniff" },
        { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
        { key: "X-Frame-Options", value: "DENY" },
        { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=(), payment=(), usb=(), interest-cohort=()" },
      ],
    }];
  },
  async rewrites() {
    // Normaliza para evitar barras duplicadas si la variable trae / al final
    const apiUrl = (process.env.BACKEND_INTERNAL_URL || process.env.NEXT_PUBLIC_API_URL)
      ?.replace(/\/+$/, "");
    const modules = ["accounts", "audit", "catalog", "harvesting", "journals", "platforms"];

    return modules.flatMap((module) => [
      // 1. Ruta base exacta del módulo (ej: /api/journals/ -> /api/journals/)
      {
        source: `/api/${module}/`,
        destination: `${apiUrl}/api/${module}/`,
      },
      // 2. Subrutas del módulo (ej: /api/journals/public/ -> /api/journals/public/)
      {
        source: `/api/${module}/:path+`,
        destination: `${apiUrl}/api/${module}/:path+/`,
      },
    ]);
  },
};

export default nextConfig;
