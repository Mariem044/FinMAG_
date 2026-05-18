import { create } from "zustand";
import { persist } from "zustand/middleware";

const USE_MOCK_AUTH = import.meta.env?.VITE_USE_MOCK_AUTH !== "false";
const API_BASE = (import.meta.env?.VITE_API_URL || "").replace(/\/$/, "");

// ROLE_PROFILES loaded from env or remote config in production
const _ROLE_PROFILES_FALLBACK = [
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
    bio: "Responsable de l'analyse financiere et du suivi des indicateurs pour MAG Distribution.",
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
    bio: "Responsable des equipes commerciales region Sud.",
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
    bio: "Specialise dans l'analyse des donnees de ventes et de tresorerie.",
    avatar: null,
    initiales: "KM",
    actif: true,
  },
  {
    id: "usr-004",
    prenom: "Nadia",
    nom: "Mansouri",
    email: "nadia.mansouri@magdistribution.tn",
    password: "Consultant@2024",
    telephone: "+216 95 432 109",
    poste: "Consultante BI",
    departement: "Direction",
    role: "Consultant",
    localisation: "Tunis, Tunisie",
    bio: "Profil de consultation limite aux vues commerciales et aux pages d'assistance.",
    avatar: null,
    initiales: "NM",
    actif: true,
  },
  {
    id: "usr-005",
    prenom: "Youssef",
    nom: "Jebali",
    email: "youssef.jebali@magdistribution.tn",
    password: "Auditeur@2024",
    telephone: "+216 94 321 098",
    poste: "Auditeur Interne",
    departement: "Comptabilite",
    role: "Auditeur",
    localisation: "Tunis, Tunisie",
    bio: "Profil dedie au controle fiscal, bancaire et aux exports autorises.",
    avatar: null,
    initiales: "YJ",
    actif: true,
  },
];

const ROLE_PROFILES =
  typeof import.meta.env?.VITE_ROLE_PROFILES === "string"
    ? JSON.parse(import.meta.env.VITE_ROLE_PROFILES)
    : _ROLE_PROFILES_FALLBACK;

export const ENTRY_ROLES = ROLE_PROFILES.map(({ password: _password, ...user }) => user);

const MOCK_USERS = ROLE_PROFILES;

export const ROLE_PERMISSIONS =
  typeof import.meta.env?.VITE_ROLE_PERMISSIONS === "string"
    ? JSON.parse(import.meta.env.VITE_ROLE_PERMISSIONS)
    : {
  Administrateur: {
    canViewAll: true,
    canEditUsers: true,
    canExport: true,
    canChangeSettings: true,
    routes: ["*"],
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
      "/predictions",
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
      "/predictions",
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
    routes: ["/", "/ventes", "/acteurs", "/predictions", "/profil", "/aide", "/parametres"],
  },
  Auditeur: {
    canViewAll: false,
    canEditUsers: false,
    canExport: true,
    canChangeSettings: false,
    routes: ["/", "/fiscalite", "/banque", "/predictions", "/profil", "/aide", "/parametres"],
  },
};

function verifyMockPassword(plain, stored) {
  return plain === stored;
}

function generateSessionToken(prefix = "session") {
  let token;
  if (typeof crypto === "undefined" || !crypto.getRandomValues) {
    token = Math.random().toString(36).slice(2) + Date.now().toString(36);
  } else {
    token = Array.from(crypto.getRandomValues(new Uint8Array(32)))
      .map((b) => b.toString(16).padStart(2, "0"))
      .join("");
  }
  return `${prefix}-${token}`;
}

function buildInitials(prenom = "", nom = "") {
  return `${prenom?.[0] || ""}${nom?.[0] || ""}`.toUpperCase() || "FM";
}

function sanitizeUser(user) {
  const { password: _password, ...safeUser } = user;
  return {
    ...safeUser,
    initiales: safeUser.initiales || buildInitials(safeUser.prenom, safeUser.nom),
  };
}

export const useAuth = create()(
  persist(
    (set, get) => ({
      user: null,
      sessionToken: null,
      isAuthenticated: false,
      loginError: null,
      isLoading: false,

      enterAsRole: async (role = "Administrateur") => {
        set({ isLoading: true, loginError: null });
        await new Promise((r) => setTimeout(r, 250));

        const profile = ROLE_PROFILES.find((u) => u.role === role) || ROLE_PROFILES[0];
        set({
          user: sanitizeUser(profile),
          sessionToken: generateSessionToken("passwordless"),
          isAuthenticated: true,
          loginError: null,
          isLoading: false,
        });

        return true;
      },

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

        await new Promise((r) => setTimeout(r, 800));

        const found = MOCK_USERS.find((u) => u.email.toLowerCase() === email.toLowerCase().trim());

        if (!found) {
          set({ isLoading: false, loginError: "Adresse email introuvable." });
          return false;
        }

        if (!found.actif) {
          set({
            isLoading: false,
            loginError: "Ce compte est desactive. Contactez l'administrateur.",
          });
          return false;
        }

        if (!verifyMockPassword(password, found.password)) {
          set({ isLoading: false, loginError: "Mot de passe incorrect." });
          return false;
        }

        set({
          user: sanitizeUser(found),
          sessionToken: generateSessionToken(),
          isAuthenticated: true,
          loginError: null,
          isLoading: false,
        });

        return true;
      },

      logout: () => {
        set({ user: null, sessionToken: null, isAuthenticated: false, loginError: null });
      },

      updateProfile: (updates) => {
        const { user } = get();
        if (!user) return;
        const nextUser = { ...user, ...updates };
        set({ user: { ...nextUser, initiales: buildInitials(nextUser.prenom, nextUser.nom) } });
      },

      changePassword: async (currentPassword, newPassword) => {
        const { user, sessionToken } = get();
        if (!user) return { success: false, error: "Non authentifie." };

        if (sessionToken?.startsWith("passwordless-")) {
          return {
            success: false,
            error: "Le mot de passe n'est plus necessaire pour entrer dans l'application.",
          };
        }

        await new Promise((r) => setTimeout(r, 600));

        const found = MOCK_USERS.find((u) => u.id === user.id);
        if (!found || !verifyMockPassword(currentPassword, found.password)) {
          return { success: false, error: "Mot de passe actuel incorrect." };
        }

        found.password = newPassword;
        return { success: true };
      },

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

      partialize: (state) => ({
        user: state.user,
        sessionToken: state.sessionToken,
        isAuthenticated: state.isAuthenticated,
      }),
    },
  ),
);
