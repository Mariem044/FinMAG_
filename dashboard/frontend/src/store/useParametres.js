import { create } from "zustand";
import { persist } from "zustand/middleware";

// Paramètres de base de l'application
export const useParametres = create()(
  persist(
    (set) => ({
      langue: "Français",
      devise: "TND - Dinar Tunisien",

      setLangue: (langue) => set({ langue }),
      setDevise: (devise) => set({ devise }),

      // locale pour le formatage des nombres
      locale: () => "fr-TN",
    }),
    {
      name: "finmag-parametres",
    },
  ),
);
