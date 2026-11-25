"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import "flag-icons/css/flag-icons.min.css";
import { filterFlagCountries, FLAG_COUNTRIES } from "./flagCountries.js";

const focus = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#7f1218]";
const GRID_COLUMNS = 7;

function getPopoverPosition(rect) {
  const width = Math.min(360, window.innerWidth - 16);
  const maxHeight = Math.min(360, window.innerHeight - 16);
  const left = Math.max(8, Math.min(rect.left, window.innerWidth - width - 8));
  const belowTop = rect.bottom + 8;
  const top = belowTop + maxHeight <= window.innerHeight - 8 || rect.top < maxHeight + 16
    ? Math.min(belowTop, window.innerHeight - maxHeight - 8)
    : rect.top - maxHeight - 8;
  return { left, top: Math.max(8, top), width, maxHeight };
}

function FlagIcon({ code, name, className = "" }) {
  return (
    <span
      aria-hidden="true"
      title={name}
      className={`fi fi-${code.toLocaleLowerCase("en")} ${className}`}
      style={{ display: "inline-block", width: "1.75rem", height: "1.25rem", flexShrink: 0 }}
    />
  );
}

/**
 * @param {{
 *   value: string;
 *   onChange: (value: string) => void;
 *   onSelectCountry?: (country: { code: string; name: string; emoji: string }) => void;
 *   invalid?: boolean;
 *   labelledBy?: string;
 *   describedBy?: string;
 * }} props
 */
export default function FlagPicker({ value, onChange, onSelectCountry, invalid = false, labelledBy, describedBy }) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const [position, setPosition] = useState(null);
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const popoverRef = useRef(null);
  const searchRef = useRef(null);
  const optionRefs = useRef([]);
  const countries = useMemo(() => filterFlagCountries(search), [search]);
  const selectedCountry = FLAG_COUNTRIES.find((country) => country.emoji === value);
  const popoverId = "catalog-flag-picker-options";

  const closePicker = useCallback((returnFocus = false) => {
    setOpen(false);
    if (returnFocus) requestAnimationFrame(() => triggerRef.current?.focus());
  }, []);

  function openPicker() {
    const rect = triggerRef.current?.getBoundingClientRect();
    if (!rect) return;
    setSearch("");
    setActiveIndex(Math.max(0, FLAG_COUNTRIES.findIndex((country) => country.emoji === value)));
    setPosition(getPopoverPosition(rect));
    setOpen(true);
  }

  function selectCountry(country) {
    onChange(country.emoji);
    onSelectCountry?.(country);
    closePicker(true);
  }

  useEffect(() => {
    if (!open) return undefined;
    let positionFrame;
    const focusFrame = requestAnimationFrame(() => searchRef.current?.focus());
    const reposition = () => {
      cancelAnimationFrame(positionFrame);
      positionFrame = requestAnimationFrame(() => {
        const rect = triggerRef.current?.getBoundingClientRect();
        if (rect) setPosition(getPopoverPosition(rect));
      });
    };
    const onPointerDown = (event) => {
      if (!rootRef.current?.contains(event.target) && !popoverRef.current?.contains(event.target)) {
        closePicker();
      }
    };
    window.addEventListener("resize", reposition);
    window.addEventListener("scroll", reposition, true);
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      cancelAnimationFrame(focusFrame);
      cancelAnimationFrame(positionFrame);
      window.removeEventListener("resize", reposition);
      window.removeEventListener("scroll", reposition, true);
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [closePicker, open]);

  function focusOption(index) {
    if (index < 0 || index >= countries.length) return;
    setActiveIndex(index);
    optionRefs.current[index]?.focus();
  }

  function onSearchKeyDown(event) {
    if (event.key === "ArrowDown" && countries.length) {
      event.preventDefault();
      focusOption(0);
    } else if (event.key === "ArrowUp" && countries.length) {
      event.preventDefault();
      focusOption(countries.length - 1);
    } else if (event.key === "Enter" && countries.length) {
      event.preventDefault();
      selectCountry(countries[Math.min(activeIndex, countries.length - 1)]);
    } else if (event.key === "Escape") {
      event.preventDefault();
      closePicker(true);
    }
  }

  function onOptionKeyDown(event, index) {
    let nextIndex = index;
    if (event.key === "ArrowDown") nextIndex += GRID_COLUMNS;
    else if (event.key === "ArrowUp") nextIndex -= GRID_COLUMNS;
    else if (event.key === "ArrowRight") nextIndex += 1;
    else if (event.key === "ArrowLeft") nextIndex -= 1;
    else if (event.key === "Escape") {
      event.preventDefault();
      closePicker(true);
      return;
    } else {
      return;
    }
    event.preventDefault();
    focusOption(nextIndex);
  }

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={popoverId}
        aria-labelledby={labelledBy}
        aria-describedby={describedBy}
        onClick={() => (open ? closePicker() : openPicker())}
        className={`mt-1 flex min-h-10 w-full items-center gap-3 rounded-md border bg-white px-3 py-2 text-left text-sm text-slate-800 ${focus} ${
          invalid ? "border-rose-500" : "border-slate-300"
        }`}
      >
        {selectedCountry ? <FlagIcon code={selectedCountry.code} name={selectedCountry.name} /> : <span className="h-5 w-7 rounded-sm bg-slate-100" aria-hidden="true" />}
        <span className="flex-1">{selectedCountry?.name || "Seleccionar bandera"}</span>
        <span aria-hidden="true" className="text-slate-500">▾</span>
      </button>
      <div aria-live="polite" className="mt-2 inline-flex items-center gap-2 text-sm text-slate-600">
        Vista previa:
        {selectedCountry
          ? <FlagIcon code={selectedCountry.code} name={selectedCountry.name} className="text-base" />
          : <span>{value || "—"}</span>}
      </div>
      {open && position && createPortal(
        <div
          ref={popoverRef}
          id={popoverId}
          role="listbox"
          aria-label="Banderas de países"
          className="fixed z-[100] flex flex-col overflow-hidden rounded-lg border border-slate-200 bg-white shadow-xl"
          style={{ left: position.left, top: position.top, width: position.width, maxHeight: position.maxHeight }}
        >
          <div className="border-b border-slate-200 p-3">
            <label htmlFor="catalog-flag-picker-search" className="sr-only">Buscar país por nombre o código ISO</label>
            <input
              ref={searchRef}
              id="catalog-flag-picker-search"
              type="search"
              autoComplete="off"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setActiveIndex(0);
              }}
              onKeyDown={onSearchKeyDown}
              placeholder="Buscar país o código ISO…"
              className={`w-full rounded-md border border-slate-300 px-3 py-2 text-sm ${focus}`}
            />
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {countries.length ? (
              <div className="grid grid-cols-7 gap-1">
                {countries.map((country, index) => {
                  const selected = country.emoji === value;
                  return (
                    <button
                      key={country.code}
                      ref={(element) => { optionRefs.current[index] = element; }}
                      type="button"
                      role="option"
                      aria-label={`${country.name}, ${country.code}`}
                      aria-selected={selected}
                      title={`${country.name} (${country.code})`}
                      tabIndex={activeIndex === index ? 0 : -1}
                      onFocus={() => setActiveIndex(index)}
                      onKeyDown={(event) => onOptionKeyDown(event, index)}
                      onClick={() => selectCountry(country)}
                      className={`flex min-h-12 flex-col items-center justify-center gap-1 rounded-md border text-xs ${focus} ${
                        selected
                          ? "border-[#7f1218] bg-rose-50 ring-1 ring-[#7f1218]"
                          : "border-transparent hover:border-slate-200 hover:bg-slate-50"
                      }`}
                    >
                      <FlagIcon code={country.code} name={country.name} />
                      <span className="text-[10px] font-medium text-slate-600">{country.code}</span>
                    </button>
                  );
                })}
              </div>
            ) : (
              <p className="px-2 py-6 text-center text-sm text-slate-600">No se encontraron países.</p>
            )}
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
