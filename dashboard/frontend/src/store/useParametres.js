import { create } from "zustand";
import { persist } from "zustand/middleware";

// Store minimaliste — langue/devise supprimés (non utilisés dans l'UI)
// Conservé pour compatibilité si d'autres modules l'importent
export const useParametres = create()(
  persist(
    (set) => ({
      // locale pour le formatage des nombres (toujours fr-TN pour FinMAG Tunisie)
      locale: () => "fr-TN",
    }),
    {
      name: "finmag-parametres",
    },
  ),
);
