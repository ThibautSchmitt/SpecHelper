"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme, type ThemePreference } from "@/lib/theme";
import { useI18n } from "@/lib/i18n";

export function ThemeControl() {
  const { preference, setPreference, storageAvailable } = useTheme();
  const { t } = useI18n();
  return (
    <div>
      <span className="mb-2 block text-sm font-medium" id="theme-label">
        {t("Theme")}
      </span>
      <div className="theme-options" role="group" aria-labelledby="theme-label">
        {(
          [
            ["light", "Light", Sun],
            ["dark", "Dark", Moon],
            ["system", "System", Monitor],
          ] as const
        ).map(([value, label, Icon]) => (
          <button
            key={value}
            type="button"
            aria-pressed={preference === value}
            onClick={() => setPreference(value as ThemePreference)}
          >
            <Icon size={16} />
            {t(label)}
          </button>
        ))}
      </div>
      <p className="mt-2 text-xs muted">
        {t(
          storageAvailable
            ? "Saved in this browser. System follows your device appearance."
            : "Theme is applied for this tab. Browser storage is unavailable.",
        )}
      </p>
    </div>
  );
}
