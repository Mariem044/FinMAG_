import { create } from "zustand";
import { persist } from "zustand/middleware";
import { translations, langCodeMap } from "@/i18n/Translation";

export const useParametres = create()(
  persist(
    (set, get) => ({
      langue: "Français",
      devise: "TND - Dinar Tunisien",

      setLangue: (langue) => {
        set({ langue });
        const code = langCodeMap[langue] ?? "fr";
        document.documentElement.setAttribute("lang", code);
        document.documentElement.setAttribute("dir", code === "ar" ? "rtl" : "ltr");
      },
      setDevise: (devise) => set({ devise }),

      t: (key) => {
        const code = langCodeMap[get().langue] ?? "fr";
        return translations[code]?.[key] ?? translations["fr"][key] ?? key;
      },
    }),
    { name: "finmag-parametres" },
  ),
);

export function applyStoredLanguage() {
  try {
    const stored = JSON.parse(localStorage.getItem("finmag-parametres") || "{}");
    const langue = stored?.state?.langue;
    if (langue) {
      const code = langCodeMap[langue] ?? "fr";
      document.documentElement.setAttribute("lang", code);
      document.documentElement.setAttribute("dir", code === "ar" ? "rtl" : "ltr");
    }
  } catch {}
}
