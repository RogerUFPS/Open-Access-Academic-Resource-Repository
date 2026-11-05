"use client";

import React, { Suspense, useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useAccountsApi } from "@/shared/components/AccountsProvider";
import { 
  LayoutGrid, 
  Book, 
  RefreshCw, 
  Bell, 
  Clock, 
  Users, 
  Trash2, 
  Cpu, 
  Tag, 
  MessageSquare, 
  LogOut, 
  Menu, 
  X 
} from "lucide-react";
import { getLinkAlerts } from "@/features/admin/harvesting/harvesting";

export default function AdminLayout({ children, userName = "Usuario" }) {
  return (
    <Suspense fallback={<div role="status" className="p-8">Cargando administración…</div>}>
      <AdminLayoutContent userName={userName}>{children}</AdminLayoutContent>
    </Suspense>
  );
}

function AdminLayoutContent({ children, userName }) {
  const accountsApi = useAccountsApi();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const presetsView = ["presets", "crear-preset", "editar-preset"].includes(searchParams.get("vista"));
  const router = useRouter();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const [sessionError, setSessionError] = useState("");
  const [alertCount, setAlertCount] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    let timer;
    const loadAlerts = async () => {
      try {
        const alerts = await getLinkAlerts({ current: "true", failure_confirmed: "true" }, controller.signal);
        if (!controller.signal.aborted) setAlertCount(alerts.length);
      } catch {
        // The notification bell is passive; a temporary API failure should not interrupt navigation.
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(loadAlerts, 60000);
      }
    };
    loadAlerts();
    return () => { controller.abort(); clearTimeout(timer); };
  }, []);

  const alertsHref = "/admin/alertas?current=true&failure_confirmed=true";
  
  // Cálculo dinámico de iniciales (De tu versión)
  const userInitials = userName.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part.charAt(0)).join("").toLocaleUpperCase("es");

  async function signOut() {
    if (signingOut) return;
    setSigningOut(true);
    setSessionError("");
    try {
      await accountsApi.logout();
      setSidebarOpen(false);
      router.replace("/admin/login");
      router.refresh();
    } catch (error) {
      setSessionError(error.message);
      setSigningOut(false);
    }
  }

  // Mapeo de rutas fusionado (Tus rutas + Sintaxis válidas y Papelera)
  const menuGroups = [
    {
      title: "DIRECTORIO",
      items: [
        { name: "Indicadores", href: "/admin/indicadores", icon: LayoutGrid },
        { name: "Recursos", href: "/admin/bases-de-datos", icon: Book },
        { name: "Sintaxis válidas", href: "/admin/sintaxis-validas", icon: Book },
        { name: "Cosecha", href: "/admin/cosecha", icon: RefreshCw },
      ]
    },
    {
      title: "GOBIERNO",
      items: [
        { name: "Bitácora", href: "/admin/bitacora", icon: Clock },
        { name: "Administrativos", href: "/admin/usuarios", icon: Users },
        { name: "Presets", href: "/admin/usuarios?vista=presets", icon: Users },
        { name: "Papelera", href: "/admin/papelera", icon: Trash2 },
      ]
    },
    {
      title: "INTELIGENCIA",
      items: [
        { name: "Módulo de IA", href: "/admin/modulo-ia", icon: Cpu },
        { name: "Clasificación", href: "/admin/areas-conocimiento", icon: Tag }, 
        { name: "Chats", href: "/admin/chats", icon: MessageSquare },
      ]
    }
  ];

  return (
    <div className="min-h-screen bg-[#F4F5F8] text-gray-900 flex flex-col md:flex-row antialiased font-sans">
      
      {/* Mobile Top Navbar - Color actualizado a oscuro */}
      <div className="md:hidden bg-[#7f1218] px-4 py-3 flex items-center justify-between sticky top-0 z-40 text-white shadow-md">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-white/10 border border-white/20 flex items-center justify-center font-bold text-sm">
            UF
          </div>
          <div>
            <span className="font-semibold text-sm tracking-tight block">Biblioteca UFPS</span>
          </div>
        </div>
        <div className="flex items-center gap-1">
          <Link href={alertsHref} aria-label={`Alertas de enlaces${alertCount ? `: ${alertCount} confirmadas` : ""}`} className="relative rounded-lg p-2 text-white hover:bg-white/10">
            <Bell className="h-5 w-5" />
            {alertCount > 0 && <span className="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-[#F59E0B] px-1 text-center text-[10px] leading-4 font-bold text-[#321B00]">{alertCount > 99 ? "99+" : alertCount}</span>}
          </Link>
          <button
            onClick={() => setSidebarOpen(!sidebarOpen)}
            className="p-2 rounded-lg text-white hover:bg-white/10 focus:outline-none transition-colors"
            aria-label={sidebarOpen ? "Cerrar menú" : "Abrir menú"}
          >
            {sidebarOpen ? <X className="w-6 h-6" /> : <Menu className="w-6 h-6" />}
          </button>
        </div>
      </div>

      {/* Sidebar - Color oscuro de producción pero conservando tus clases responsive (h-dvh, md:sticky) */}
      <aside
        className={`fixed inset-y-0 left-0 z-50 h-dvh w-64 shrink-0 bg-[#7f1218] flex flex-col justify-between transform transition-transform duration-200 ease-in-out md:translate-x-0 ${
          sidebarOpen ? "translate-x-0" : "-translate-x-full"
        } md:sticky md:top-0 md:self-start md:z-auto`}
      >
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain no-scrollbar pb-6">
          {/* Logo & Header */}
          <div className="p-6 flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-white/10 border border-white/10 flex items-center justify-center text-white font-medium text-lg shrink-0">
              UF
            </div>
            <div>
              <h1 className="font-medium text-white text-base tracking-tight leading-none">Biblioteca UFPS</h1>
              <p className="text-[11px] text-white/70 mt-1">Directorio de acceso abierto</p>
            </div>
          </div>

          {/* Navigation Groups */}
          <div className="px-3 space-y-6">
            {menuGroups.map((group, groupIndex) => (
              <nav key={groupIndex} className="space-y-1">
                <p className="px-4 text-[10px] font-bold text-white/50 uppercase tracking-widest mb-3">
                  {group.title}
                </p>
                {group.items.map((item) => {
                  const Icon = item.icon;
                  // Manejo de estado activo
                  const isActive = item.name === "Presets" ? pathname === "/admin/usuarios" && presetsView
                    : item.name === "Administrativos" ? pathname.startsWith(item.href) && !presetsView
                    : pathname.startsWith(item.href);

                  return (
                    <Link
                      key={item.href}
                      href={item.href}
                      onClick={() => setSidebarOpen(false)}
                      className={`flex items-center gap-3 px-4 py-2.5 rounded-xl text-sm font-medium transition-all relative ${
                        isActive
                          ? "bg-white/15 text-white"
                          : "text-white/70 hover:bg-white/5 hover:text-white"
                      }`}
                    >
                      {/* Indicador visual lateral para la ruta activa */}
                      {isActive && (
                        <div className="absolute left-0 top-1/2 -translate-y-1/2 w-1 h-6 bg-white rounded-r-md" />
                      )}
                      <Icon className={`w-4 h-4 ${isActive ? "text-white" : "text-white/70"}`} />
                      <span>{item.name}</span>
                    </Link>
                  );
                })}
              </nav>
            ))}
          </div>
        </div>

        {/* User Footer - Conservando tu lógica dinámica y accesibilidad pero con el color de texto oscuro */}
        <div className="shrink-0 p-4 mt-auto">
          <Link href={alertsHref} onClick={() => setSidebarOpen(false)} className="mb-3 flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium text-white/85 transition-colors hover:bg-white/10 hover:text-white">
            <span className="relative inline-flex"><Bell className="h-4 w-4" />{alertCount > 0 && <span className="absolute -right-2 -top-2 h-2.5 w-2.5 rounded-full border border-[#7f1218] bg-[#F59E0B]" />}</span>
            <span>Alertas de enlaces</span>
            {alertCount > 0 && <span className="ml-auto rounded-full bg-[#F59E0B] px-2 py-0.5 text-xs font-bold text-[#321B00]">{alertCount > 99 ? "99+" : alertCount}</span>}
          </Link>
          <button type="button" onClick={signOut} disabled={signingOut} aria-label={`Cerrar sesión de ${userName}`} className="w-full text-left disabled:opacity-60">
            <div className="flex items-center justify-between p-3 rounded-xl bg-white/10 hover:bg-white/15 transition-colors cursor-pointer group">
              <div className="min-w-0 flex items-center gap-3">
                <div aria-hidden="true" className="w-9 h-9 rounded-full bg-[#EADDD7] text-[#7f1218] font-medium text-sm flex items-center justify-center shrink-0">
                  {userInitials}
                </div>
                <div className="min-w-0">
                  <p title={userName} className="text-sm font-medium text-white truncate">{userName}</p>
                  <p className="text-[11px] text-white/70 group-hover:text-white/90 transition-colors truncate">
                    {signingOut ? "Cerrando sesión…" : "Cerrar sesión"}
                  </p>
                </div>
              </div>
              <LogOut className="ml-2 w-4 h-4 shrink-0 text-white/70 group-hover:text-white transition-colors" />
            </div>
          </button>
          {sessionError && <p role="alert" className="mt-2 text-xs text-white">{sessionError}</p>}
        </div>
      </aside>

      {/* Backdrop overlay for mobile sidebar */}
      {sidebarOpen && (
        <div
          onClick={() => setSidebarOpen(false)}
          className="fixed inset-0 bg-black/40 z-40 md:hidden backdrop-blur-sm"
        />
      )}

      {/* Main Content Area */}
      <main className="flex-1 min-w-0 p-4 md:p-8 w-full max-w-7xl mx-auto">
        {children}
      </main>
    </div>
  );
}