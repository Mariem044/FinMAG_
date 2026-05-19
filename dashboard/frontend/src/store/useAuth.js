import { create } from "zustand";
import { persist } from "zustand/middleware";

// Utilisateur admin de démonstration
const ADMIN_USER = {
  id: "usr-001",
  prenom: "Marie",
  nom: "Admin",
  email: "admin@finmag.tn",
  poste: "Administrateur",
  role: "Administrateur",
  initiales: "MA",
};

export const useAuth = create()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,

      // Connexion rapide en tant qu'admin
      enterAsAdmin: () => {
        set({
          user: ADMIN_USER,
          isAuthenticated: true,
        });
      },

      logout: () => {
        set({ user: null, isAuthenticated: false });
      },
    }),
    {
      name: "finmag-auth",
      partialize: (state) => ({
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
);
