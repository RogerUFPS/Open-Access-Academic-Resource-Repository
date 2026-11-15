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
