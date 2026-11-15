import { Source_Sans_3 } from "next/font/google";
import { connection } from "next/server";
import SessionExpiredProvider from "@/shared/components/SessionExpiredProvider";
import { ToastProvider } from "@/components/ui/use-toast";
import { Toaster } from "@/components/ui/toaster";
import "./globals.css";

const sourceSans = Source_Sans_3({
  variable: "--font-source-sans",
  subsets: ["latin"],
  weight: ["400", "500", "600", "700"],
});

export const metadata = {
  title: "Repositorio Biblioteca",
  description: "Portal del repositorio de biblioteca",
};

export default async function RootLayout({ children }) {
  // La CSP usa un nonce por respuesta, que sólo existe con renderizado dinámico.
  await connection();
  return (
    <html lang="es" className={`${sourceSans.variable} h-full antialiased`}>
      <body className="min-h-full flex flex-col">
        <ToastProvider>
          <SessionExpiredProvider>{children}</SessionExpiredProvider>
          <Toaster />
        </ToastProvider>
      </body>
    </html>
  );
}
