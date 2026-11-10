"use client";

import { useEffect, useState } from "react";

function getImageUrl(url) {
  if (!url || typeof url !== "string") return "";

  const trimmedUrl = url.trim();
  if (!trimmedUrl) return "";
  if (/^(https?:)?\/\//i.test(trimmedUrl)) {
    return trimmedUrl.startsWith("//") ? `https:${trimmedUrl}` : trimmedUrl;
  }

  const apiBaseUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, "");
  if (apiBaseUrl && trimmedUrl.startsWith("/")) {
    return `${apiBaseUrl}${trimmedUrl}`;
  }
  return trimmedUrl;
}

export default function ResourceThumb({
  src,
  thumbnailSrc,
  name,
  fallback,
  className = "",
  imageClassName = "",
  loading,
}) {
  const imageUrl = getImageUrl(thumbnailSrc) || getImageUrl(src);
  const [failedSrc, setFailedSrc] = useState("");

  useEffect(() => {
    setFailedSrc("");
  }, [imageUrl]);

  if (!imageUrl || failedSrc === imageUrl) {
    return (
      <span
        aria-hidden="true"
        className={`grid shrink-0 place-items-center rounded-md bg-[#f8eeee] text-sm font-bold text-[#7f1218] ${className}`}
      >
        {fallback}
      </span>
    );
  }

  return (
    <img
      alt={`Logo de ${name}`}
      className={`object-contain ${imageClassName || className}`}
      src={imageUrl}
      loading={loading}
      onError={() => setFailedSrc(imageUrl)}
    />
  );
}
