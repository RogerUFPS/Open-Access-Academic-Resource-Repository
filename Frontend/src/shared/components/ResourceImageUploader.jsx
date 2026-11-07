"use client";

import { useEffect, useRef, useState } from "react";
import { extractApiErrorText } from "@/shared/services/apiClient";

const MAX_SIZE = 5 * 1024 * 1024;
const ACCEPTED_TYPES = ["image/jpeg", "image/png", "image/gif", "image/webp"];

export function ResourceImageUploader({
  value,
  alt,
  resourceId,
  uploadImage,
  deleteImage,
  onImageChange,
  onPendingFileChange,
}) {
  const inputRef = useRef(null);
  const objectUrlRef = useRef(null);
  const [preview, setPreview] = useState(value || null);
  const [broken, setBroken] = useState(false);
  const [selectedFile, setSelectedFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!objectUrlRef.current) {
      setPreview(value || null);
      setBroken(false);
    }
  }, [value]);

  useEffect(() => () => {
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
  }, []);

  const selectFile = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    setError("");
    if (!ACCEPTED_TYPES.includes(file.type)) {
      setError("Formato no permitido. Usa JPEG, PNG, GIF o WebP.");
      return;
    }
    if (file.size > MAX_SIZE) {
      setError("La imagen supera el tamaño máximo permitido (5 MB).");
      return;
    }
    if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
    const objectUrl = URL.createObjectURL(file);
    objectUrlRef.current = objectUrl;
    setPreview(objectUrl);
    setBroken(false);
    setSelectedFile(file);
    onPendingFileChange?.(file);
    if (resourceId && uploadImage) {
      setUploading(true);
      try {
        const updated = await uploadImage(resourceId, file);
        URL.revokeObjectURL(objectUrl);
        objectUrlRef.current = null;
        setPreview(updated.url_image || null);
        setSelectedFile(null);
        onImageChange?.(updated.url_image || null);
        onPendingFileChange?.(null);
      } catch (err) {
        setError(imageErrorMessage(err));
      } finally {
        setUploading(false);
      }
    }
  };

  const remove = async () => {
    if (!resourceId) {
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
      setPreview(null);
      setSelectedFile(null);
      onPendingFileChange?.(null);
      onImageChange?.(null);
      return;
    }
    setUploading(true);
    setError("");
    try {
      const updated = await deleteImage(resourceId);
      setPreview(updated.url_image || null);
      setSelectedFile(null);
      onImageChange?.(updated.url_image || null);
    } catch (err) {
      setError(imageErrorMessage(err));
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="space-y-2">
      <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/gif,image/webp" onChange={selectFile} className="hidden" />
      <div className="flex items-center gap-4">
        {preview && !broken ? (
          <img src={preview} alt={alt} onError={() => setBroken(true)} className="h-24 w-24 rounded-lg object-cover" />
        ) : (
          <div className="flex h-24 w-24 items-center justify-center rounded-lg bg-slate-100 text-xs text-slate-400">Sin imagen</div>
        )}
        <div className="min-w-0 text-xs">
          <button type="button" disabled={uploading} onClick={() => inputRef.current?.click()} className="rounded-lg border px-3 py-2 font-semibold">
            {preview ? "Reemplazar" : "Seleccionar imagen"}
          </button>
          {(selectedFile || preview) && (
            <button type="button" disabled={uploading} onClick={remove} className="ml-2 rounded-lg border border-rose-200 px-3 py-2 font-semibold text-rose-700">
              Eliminar
            </button>
          )}
          {selectedFile && <p className="mt-2 truncate text-slate-600">{selectedFile.name} · {(selectedFile.size / 1024 / 1024).toFixed(2)} MB</p>}
          {uploading && <p className="mt-2 text-slate-500">Subiendo imagen…</p>}
        </div>
      </div>
      {error && <p className="text-xs text-rose-600">{error}</p>}
    </div>
  );
}

export function imageErrorMessage(error) {
  if (error?.status === 401) return "La sesión expiró. Inicia sesión nuevamente.";
  if (error?.status === 403) return "No autorizado.";
  if (error?.status === 404) return "La ficha no existe o fue eliminada.";
  if (error?.status === 415) return "Revisa el tipo de envío de la imagen.";
  if (error?.status === 503) return "Servicio de imágenes no disponible. Inténtalo nuevamente.";
  if (error?.status === 400) {
    return extractApiErrorText(error?.data?.image)
      || extractApiErrorText(error?.data?.detail || error?.data?.message)
      || "Archivo de imagen inválido.";
  }
  return error?.message || "No se pudo procesar la imagen.";
}
