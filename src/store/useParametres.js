// FIXED: Normalized persisted language values and exposed locale-aware translation helpers.
import { create } from "zustand";
import { persist } from "zustand/middleware";
import { translations, langCodeMap, localeMap, normalizeLanguage } from "@/i18n/Translation";

export const useParametres = create()(
  persist(
    (set, get) => ({
      langue: "Français",
      devise: "TND - Dinar Tunisien",

      setLangue: (langue) => {
        const normalized = normalizeLanguage(langue);
        set({ langue: normalized });
        const code = langCodeMap[normalized] ?? "fr";
        document.documentElement.setAttribute("lang", code);
        document.documentElement.setAttribute("dir", code === "ar" ? "rtl" : "ltr");
      },
      setDevise: (devise) => set({ devise }),

      t: (key) => {
        const code = langCodeMap[normalizeLanguage(get().langue)] ?? "fr";
        return translations[code]?.[key] ?? translations["fr"][key] ?? key;
      },
      locale: () => localeMap[langCodeMap[normalizeLanguage(get().langue)] ?? "fr"] ?? "fr-TN",
    }),
    { name: "finmag-parametres" },
  ),
);

export function applyStoredLanguage() {
  try {
    const stored = JSON.parse(localStorage.getItem("finmag-parametres") || "{}");
    const langue = stored?.state?.langue;
    if (langue) {
      const code = langCodeMap[normalizeLanguage(langue)] ?? "fr";
      document.documentElement.setAttribute("lang", code);
      document.documentElement.setAttribute("dir", code === "ar" ? "rtl" : "ltr");
    }
  } catch {}
}
