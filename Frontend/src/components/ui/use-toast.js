"use client";

import { createContext, useCallback, useContext, useMemo, useState } from "react";

const ToastContext = createContext(null);
let nextId = 0;

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([]);
  const dismiss = useCallback((id) => setToasts((current) => current.filter((item) => item.id !== id)), []);
  const toast = useCallback((options) => {
    const id = ++nextId;
    setToasts((current) => [...current.slice(-3), { ...options, id }]);
    return id;
  }, []);
  const value = useMemo(() => ({ toasts, toast, dismiss }), [toasts, toast, dismiss]);
  return <ToastContext.Provider value={value}>{children}</ToastContext.Provider>;
}

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) throw new Error("useToast debe usarse dentro de ToastProvider.");
  return context;
}
