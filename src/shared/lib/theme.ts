// SPDX-License-Identifier: AGPL-3.0-only
// Copyright (C) 2026 Vasudev Siddh and vasu-devs

import { useEffect, useState } from "react";

export type ThemePref = "light" | "dark" | "system";
export type ResolvedTheme = "light" | "dark";

export const THEME_KEY = "jhm-theme";

const SYSTEM_DARK = "(prefers-color-scheme: dark)";

export function getStoredPref(): ThemePref {
  try {
    const value = localStorage.getItem(THEME_KEY);
    if (value === "light" || value === "dark" || value === "system") return value;
  } catch {
    /* localStorage unavailable (private mode / sandbox) — fall back to system */
  }
  return "system";
}

export function systemTheme(): ResolvedTheme {
  return typeof window !== "undefined" && window.matchMedia(SYSTEM_DARK).matches ? "dark" : "light";
}

export function resolveTheme(pref: ThemePref): ResolvedTheme {
  return pref === "system" ? systemTheme() : pref;
}

/** Cross-instance sync: every useTheme() call site keeps its own React state,
    so a toggle in one component (Topbar) must notify the others (App, which
    stamps data-theme on the .product-app shell). Without this, the root tokens
    flip while the shell attribute goes stale — a half-themed, unreadable UI. */
export const THEME_EVENT = "jhm-theme";

/** Apply the resolved theme to <html> so the CSS token overrides take effect. */
export function applyTheme(pref: ThemePref): ResolvedTheme {
  const resolved = resolveTheme(pref);
  const root = document.documentElement;
  root.dataset.theme = resolved;
  root.style.colorScheme = resolved;
  window.dispatchEvent(new CustomEvent<ResolvedTheme>(THEME_EVENT, { detail: resolved }));
  return resolved;
}

/**
 * Wire up theming once at app start: apply the stored preference and, while the
 * preference is "system", keep following OS light/dark changes live. Mirrors the
 * inline bootstrap in index.html (which runs first to avoid a flash of the wrong
 * theme); this re-applies after hydration and adds the live system listener.
 */
export function initTheme(): void {
  applyTheme(getStoredPref());
  if (typeof window === "undefined" || !window.matchMedia) return;
  window.matchMedia(SYSTEM_DARK).addEventListener("change", () => {
    if (getStoredPref() === "system") applyTheme("system");
  });
}

/** React hook for reading and changing the theme preference. */
export function useTheme() {
  const [pref, setPrefState] = useState<ThemePref>(getStoredPref);
  const [resolved, setResolved] = useState<ResolvedTheme>(() => resolveTheme(getStoredPref()));

  const setPref = (next: ThemePref) => {
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      /* ignore persistence failure; the in-memory choice still applies */
    }
    setPrefState(next);
    setResolved(applyTheme(next));
  };

  // Follow OS changes while on "system" so the hook's `resolved` stays accurate.
  useEffect(() => {
    if (pref !== "system" || typeof window === "undefined" || !window.matchMedia) return;
    const mql = window.matchMedia(SYSTEM_DARK);
    const onChange = () => setResolved(applyTheme("system"));
    mql.addEventListener("change", onChange);
    return () => mql.removeEventListener("change", onChange);
  }, [pref]);

  // Follow theme changes made by OTHER useTheme() instances (see THEME_EVENT).
  useEffect(() => {
    const onTheme = (event: Event) => {
      setResolved((event as CustomEvent<ResolvedTheme>).detail);
      setPrefState(getStoredPref());
    };
    window.addEventListener(THEME_EVENT, onTheme);
    return () => window.removeEventListener(THEME_EVENT, onTheme);
  }, []);

  return { pref, resolved, setPref };
}
