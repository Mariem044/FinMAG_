import { create } from "zustand";
import { persist } from "zustand/middleware";
export const useTheme = create()(
  persist(
    (set, get) => ({
      isDark: true,
      toggle: () => {
        const next = !get().isDark;
        document.documentElement.classList.toggle("light", !next);
        set({ isDark: next });
      },
    }),
    { name: "finmag-theme" },
  ),
);
const LEGACY_THEME_KEY = "siad-theme";
const THEME_KEY = "finmag-theme";

export function applyStoredTheme() {
  try {
    const legacy = localStorage.getItem(LEGACY_THEME_KEY);
    if (legacy && !localStorage.getItem(THEME_KEY)) {
      localStorage.setItem(THEME_KEY, legacy);
    }

    const stored = JSON.parse(localStorage.getItem(THEME_KEY) || "{}");
    if (stored?.state?.isDark === false) {
      document.documentElement.classList.add("light");
    }
  } catch {}
}
