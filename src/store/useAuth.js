// FIXED: Separated mock auth behind VITE_USE_MOCK_AUTH and added backend login stub.
import { create } from "zustand";
import { persist } from "zustand/middleware";

const USE_MOCK_AUTH = import.meta.env?.VITE_USE_MOCK_AUTH === "true";
const API_BASE = (import.meta.env?.VITE_API_URL || "").replace(/\/$/, "");

// ─── Mock users database ──────────────────────────────────────────────────────
// Demo credentials only. Production auth must use a real backend endpoint
// with server-side password verification, hashing, rate limiting, and sessions.
const MOCK_USERS = [
  {
    id: "usr-001",
    prenom: "Ahmed",
    nom: "Dridi",
    email: "ahmed.dridi@magdistribution.tn",
    password: "Admin@2024",
    telephone: "+216 98 765 432",
    poste: "Responsable Financier",
    departement: "Finance",
    role: "Administrateur",
    localisation: "Tunis, Tunisie",
    bio: "Responsable de l'analyse financière et du suivi des KPIs pour MAG Distribution.",
    avatar: null,
    initiales: "AD",
    actif: true,
  },
  {
    id: "usr-002",
    prenom: "Sarra",
    nom: "Ben Salah",
    email: "sarra.bensalah@magdistribution.tn",
    password: "Manager@2024",
    telephone: "+216 97 654 321",
    poste: "Manager Commercial",
    departement: "Commercial",
    role: "Manager",
    localisation: "Sfax, Tunisie",
    bio: "Responsable des équipes commerciales région Sud.",
    avatar: null,
    initiales: "SB",
    actif: true,
  },
  {
    id: "usr-003",
    prenom: "Karim",
    nom: "Maaloul",
    email: "karim.maaloul@magdistribution.tn",
    password: "Analyste@2024",
    telephone: "+216 96 543 210",
    poste: "Analyste Financier",
    departement: "Finance",
    role: "Analyste",
    localisation: "Tunis, Tunisie",
    bio: "Spécialisé dans l'analyse des données de ventes et de trésorerie.",
    avatar: null,
    initiales: "KM",
    actif: true,
  },
];

// ─── Role permissions ─────────────────────────────────────────────────────────
export const ROLE_PERMISSIONS = {
  Administrateur: {
    canViewAll: true,
    canEditUsers: true,
    canExport: true,
    canChangeSettings: true,
    routes: ["*"], // all routes
  },
  Manager: {
    canViewAll: true,
    canEditUsers: false,
    canExport: true,
    canChangeSettings: false,
    routes: [
      "/",
      "/ventes",
      "/tresorerie",
      "/produits",
      "/acteurs",
      "/caisse",
      "/banque",
      "/assistant",
      "/profil",
      "/aide",
      "/parametres",
    ],
  },
  Analyste: {
    canViewAll: false,
    canEditUsers: false,
    canExport: true,
    canChangeSettings: false,
    routes: [
      "/",
      "/ventes",
      "/tresorerie",
      "/produits",
      "/acteurs",
      "/fiscalite",
      "/assistant",
      "/profil",
      "/aide",
      "/parametres",
    ],
  },
  Consultant: {
    canViewAll: false,
    canEditUsers: false,
    canExport: false,
    canChangeSettings: false,
    routes: ["/", "/ventes", "/acteurs", "/profil", "/aide", "/parametres"],
  },
  Auditeur: {
    canViewAll: false,
    canEditUsers: false,
    canExport: true,
    canChangeSettings: false,
    routes: ["/", "/fiscalite", "/banque", "/profil", "/aide", "/parametres"],
  },
};

// ─── Helpers ──────────────────────────────────────────────────────────────────
function verifyMockPassword(plain, stored) {
  return plain === stored;
}

function generateSessionToken() {
  if (typeof crypto === "undefined" || !crypto.getRandomValues) {
    return Math.random().toString(36).slice(2) + Date.now().toString(36);
  }
  return Array.from(crypto.getRandomValues(new Uint8Array(32)))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

// ─── Store ────────────────────────────────────────────────────────────────────
export const useAuth = create()(
  persist(
    (set, get) => ({
      user: null,
      sessionToken: null,
      isAuthenticated: false,
      loginError: null,
      isLoading: false,

      // ── Login ──────────────────────────────────────────────────────────────
      loginWithApi: async (email, password) => {
        const res = await fetch(`${API_BASE}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ email, password }),
        });
        if (!res.ok) {
          const body = await res.text().catch(() => "");
          throw new Error(body || "Connexion API impossible.");
        }
        return res.json();
      },

      login: async (email, password) => {
        set({ isLoading: true, loginError: null });

        if (!USE_MOCK_AUTH) {
          try {
            const result = await get().loginWithApi(email, password);
            set({
              user: result.user,
              sessionToken: result.sessionToken,
              isAuthenticated: true,
              loginError: null,
              isLoading: false,
            });
            return true;
          } catch (error) {
            set({
              isLoading: false,
              loginError: error?.message || "Connexion API impossible.",
            });
            return false;
          }
        }

        // Simulate network delay
        await new Promise((r) => setTimeout(r, 800));

        const found = MOCK_USERS.find((u) => u.email.toLowerCase() === email.toLowerCase().trim());

        if (!found) {
          set({ isLoading: false, loginError: "Adresse email introuvable." });
          return false;
        }

        if (!found.actif) {
          set({
            isLoading: false,
            loginError: "Ce compte est désactivé. Contactez l'administrateur.",
          });
          return false;
        }

        if (!verifyMockPassword(password, found.password)) {
          set({ isLoading: false, loginError: "Mot de passe incorrect." });
          return false;
        }

        const { password: _password, ...safeUser } = found;
        const sessionToken = generateSessionToken();

        set({
          user: safeUser,
          sessionToken,
          isAuthenticated: true,
          loginError: null,
          isLoading: false,
        });

        return true;
      },

      // ── Logout ─────────────────────────────────────────────────────────────
      logout: () => {
        set({ user: null, sessionToken: null, isAuthenticated: false, loginError: null });
      },

      // ── Update profile ─────────────────────────────────────────────────────
      updateProfile: (updates) => {
        const { user } = get();
        if (!user) return;
        set({ user: { ...user, ...updates } });
        // In production: PATCH /api/users/:id
      },

      // ── Change password ────────────────────────────────────────────────────
      changePassword: async (currentPassword, newPassword) => {
        const { user } = get();
        if (!user) return { success: false, error: "Non authentifié." };

        await new Promise((r) => setTimeout(r, 600));

        // Find full user record to verify current password
        const found = MOCK_USERS.find((u) => u.id === user.id);
        if (!found || !verifyMockPassword(currentPassword, found.password)) {
          return { success: false, error: "Mot de passe actuel incorrect." };
        }

        found.password = newPassword;
        return { success: true };
      },

      // ── Permission check ───────────────────────────────────────────────────
      hasPermission: (permission) => {
        const { user } = get();
        if (!user) return false;
        const perms = ROLE_PERMISSIONS[user.role];
        if (!perms) return false;
        return perms[permission] === true;
      },

      canAccessRoute: (path) => {
        const { user } = get();
        if (!user) return false;
        const perms = ROLE_PERMISSIONS[user.role];
        if (!perms) return false;
        if (perms.routes.includes("*")) return true;
        return perms.routes.some((r) => path === r || path.startsWith(r + "/"));
      },

      clearError: () => set({ loginError: null }),
    }),
    {
      name: "finmag-auth",
      // Only persist these fields — don't persist loading/error states
      partialize: (state) => ({
        user: state.user,
        sessionToken: state.sessionToken,
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
);
