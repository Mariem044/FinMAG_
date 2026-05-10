import { create } from "zustand";
import { persist } from "zustand/middleware";

// ─── Mock users database ──────────────────────────────────────────────────────
// In production, replace with real API calls
const MOCK_USERS = [
  {
    id: "usr-001",
    prenom: "Ahmed",
    nom: "Dridi",
    email: "ahmed.dridi@magdistribution.tn",
    // Demo-only hash. Production auth must be handled by a backend.
    passwordHash: "QWRtaW5AMjAyNF9maW5tYWdfc2FsdF8yMDI0",
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
    passwordHash: "TWFuYWdlckAyMDI0X2Zpbm1hZ19zYWx0XzIwMjQ=",
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
    passwordHash: "QW5hbHlzdGVAMjAyNF9maW5tYWdfc2FsdF8yMDI0",
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
function hashPassword(password) {
  // In production: use bcrypt. This is a simple demo hash.
  return btoa(password + "_finmag_salt_2024");
}

function verifyPassword(plain, stored) {
  return hashPassword(plain) === stored;
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
      login: async (email, password) => {
        set({ isLoading: true, loginError: null });

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

        if (!verifyPassword(password, found.passwordHash)) {
          set({ isLoading: false, loginError: "Mot de passe incorrect." });
          return false;
        }

        const { passwordHash: _passwordHash, ...safeUser } = found;
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
        if (!found || !verifyPassword(currentPassword, found.passwordHash)) {
          return { success: false, error: "Mot de passe actuel incorrect." };
        }

        found.passwordHash = hashPassword(newPassword);
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
