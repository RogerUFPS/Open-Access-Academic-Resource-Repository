"use client";

import { useEffect } from "react";
import { useToast } from "@/components/ui/use-toast";
import { AlertCircle, CheckCircle2, X } from "lucide-react";

export function Toaster() {
  const { toasts, dismiss } = useToast();

  useEffect(() => {
    if (!toasts.length) return undefined;
    const timers = toasts.map((item) => setTimeout(() => dismiss(item.id), item.duration || 6500));
    return () => timers.forEach(clearTimeout);
  }, [toasts, dismiss]);

  return (
    <div className="pointer-events-none fixed left-1/2 top-4 z-[100] flex w-[min(34rem,calc(100vw-2rem))] -translate-x-1/2 flex-col items-center gap-2" aria-live="polite">
      {toasts.map((item) => (
        <div key={item.id} role={item.variant === "destructive" ? "alert" : "status"} className={`pointer-events-auto flex w-full gap-3 rounded-xl border p-4 shadow-xl animate-in slide-in-from-top-4 ${item.variant === "destructive" ? "border-rose-300 bg-rose-100 text-rose-950" : "border-emerald-300 bg-emerald-50 text-gray-900"}`}>
          {item.variant === "destructive" ? <AlertCircle className="mt-0.5 h-5 w-5 shrink-0 text-rose-700" /> : <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-emerald-600" />}
          <div className="min-w-0 flex-1"><p className="font-bold">{item.title}</p>{item.description && <div className="mt-1 whitespace-pre-line text-sm leading-relaxed text-gray-700">{item.description}</div>}</div>
          <button type="button" onClick={() => dismiss(item.id)} aria-label="Cerrar notificación" className="h-fit text-gray-500 hover:text-gray-900"><X className="h-4 w-4" /></button>
        </div>
      ))}
    </div>
  );
}
