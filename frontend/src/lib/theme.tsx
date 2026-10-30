"use client";

import { createContext, useContext, useLayoutEffect, useState } from "react";

export type ThemePreference = "light" | "dark" | "system";
const storageKey = "spechelper-theme";
const valid = (value: string | null): ThemePreference =>
  value === "light" || value === "dark" || value === "system" ? value : "dark";

function luminance(rgb: number[]) {
  const values = rgb
    .map((value) => value / 255)
    .map((value) =>
      value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4,
    );
  return 0.2126 * values[0] + 0.7152 * values[1] + 0.0722 * values[2];
}

export function applyAccent(color: string) {
  if (!/^#[0-9a-f]{6}$/i.test(color)) return;
  const root = document.documentElement;
  const rgb = color
    .slice(1)
    .match(/.{2}/g)!
    .map((value) => parseInt(value, 16));
  const light = luminance(rgb);
  root.style.setProperty("--primary", color);
  root.style.setProperty(
    "--primary-foreground",
    light > 0.179 ? "#000000" : "#ffffff",
  );
  if (root.dataset.theme === "dark") {
    let ink = rgb;
    for (let amount = 0; amount <= 1; amount += 0.05) {
      ink = rgb.map((channel) =>
        Math.round(channel * (1 - amount) + 255 * amount),
      );
      if ((luminance(ink) + 0.05) / (luminance([32, 42, 60]) + 0.05) >= 4.5)
        break;
    }
    root.style.setProperty("--primary-ink", `rgb(${ink.join(" ")})`);
  } else {
    root.style.setProperty("--primary-ink", light > 0.156 ? "#172033" : color);
  }
}

function apply(preference: ThemePreference, systemDark: boolean) {
  const root = document.documentElement;
  root.dataset.theme =
    preference === "system" ? (systemDark ? "dark" : "light") : preference;
  applyAccent(root.style.getPropertyValue("--primary").trim() || "#2563eb");
}

const ThemeContext = createContext<{
  preference: ThemePreference;
  setPreference: (value: ThemePreference) => void;
  storageAvailable: boolean;
} | null>(null);

export function ThemeProvider({ children }: { children: React.ReactNode }) {
  const [preference, setValue] = useState<ThemePreference>("system");
  const [storageAvailable, setStorageAvailable] = useState(true);
  useLayoutEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    let chosen: ThemePreference = "system";
    try {
      chosen = valid(localStorage.getItem(storageKey));
    } catch {
      setStorageAvailable(false);
    }
    setValue(chosen);
    apply(chosen, media.matches);
    const update = (event: MediaQueryListEvent) => apply(chosen, event.matches);
    const storage = (event: StorageEvent) => {
      if (event.key !== storageKey && event.key !== null) return;
      chosen = valid(event.newValue);
      setValue(chosen);
      apply(chosen, media.matches);
    };
    const change = () => {
      chosen = valid(document.documentElement.dataset.themePreference || null);
      apply(chosen, media.matches);
    };
    media.addEventListener("change", update);
    window.addEventListener("storage", storage);
    window.addEventListener("theme-preference-updated", change);
    return () => {
      media.removeEventListener("change", update);
      window.removeEventListener("storage", storage);
      window.removeEventListener("theme-preference-updated", change);
    };
  }, []);
  function setPreference(value: ThemePreference) {
    setValue(value);
    document.documentElement.dataset.themePreference = value;
    try {
      localStorage.setItem(storageKey, value);
      setStorageAvailable(true);
    } catch {
      setStorageAvailable(false);
    }
    apply(value, window.matchMedia("(prefers-color-scheme: dark)").matches);
    window.dispatchEvent(new Event("theme-preference-updated"));
  }
  return (
    <ThemeContext.Provider
      value={{ preference, setPreference, storageAvailable }}
    >
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme() {
  const value = useContext(ThemeContext);
  if (!value) throw new Error("Theme controls require ThemeProvider");
  return value;
}
