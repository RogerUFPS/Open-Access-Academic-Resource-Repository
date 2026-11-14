"use client";

import { useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function LoginField({ id, label, type = "text", ...props }) {
  const [isVisible, setIsVisible] = useState(false);
  const isPassword = type === "password";
  return <div className="space-y-2 rounded-md border border-gray-200 px-3 py-2 shadow-sm focus-within:border-gray-400 focus-within:ring-1 focus-within:ring-gray-400">
    <Label htmlFor={id} className="text-[11px] font-medium tracking-wider text-gray-500 uppercase">{label}</Label>
    <div className="relative flex items-center">
      <Input id={id} required type={isPassword && isVisible ? "text" : type} className="h-7 border-0 p-0 pr-8 text-base shadow-none placeholder:text-gray-400 focus-visible:ring-0" {...props} />
      {isPassword && <button
        type="button"
        onClick={() => setIsVisible((visible) => !visible)}
        className="absolute right-0 flex h-7 w-7 items-center justify-center rounded-md text-gray-500 transition-colors hover:text-gray-800 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-gray-400"
        aria-label={isVisible ? "Ocultar contraseña" : "Mostrar contraseña"}
        aria-pressed={isVisible}
      >
        {isVisible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
      </button>}
    </div>
  </div>;
}
