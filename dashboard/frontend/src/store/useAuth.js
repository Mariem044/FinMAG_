import { create } from "zustand";
import { persist } from "zustand/middleware";

export const useAuth = create()(
  persist(
    (set) => ({
      user: null,
      isAuthenticated: false,

      // Connexion rapide en tant qu'admin
      enterAsAdmin: () => {
        set({
          user: null,
          isAuthenticated: true,
        });
      },

      logout: () => {
        set({ user: null, isAuthenticated: false });
      },
    }),
    {
      name: "finmag-auth",
      merge: (persistedState, currentState) => {
        const isAuthenticated =
          persistedState?.isAuthenticated ?? persistedState?.state?.isAuthenticated;
        return {
          ...currentState,
          isAuthenticated: Boolean(isAuthenticated),
          user: null,
        };
      },
      partialize: (state) => ({
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
);
