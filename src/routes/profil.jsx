import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef } from "react";
import {
  User,
  Mail,
  Phone,
  Building2,
  MapPin,
  Lock,
  Camera,
  Save,
  X,
  CheckCircle,
  AlertCircle,
  Eye,
  EyeOff,
  Trash2,
  Edit3,
  Shield,
  LogOut,
} from "lucide-react";
import { useAuth, ROLE_PERMISSIONS } from "@/store/useAuth";
import { useNavigate } from "@tanstack/react-router";

export const Route = createFileRoute("/profil")({
  component: ProfilPage,
});

const ROLES = ["Administrateur", "Manager", "Analyste", "Consultant", "Auditeur"];
const DEPARTMENTS = ["Finance", "Commercial", "Logistique", "IT", "Direction", "Comptabilité"];

function Toast({ message, type, onClose }) {
  return (
    <div
      className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-5 py-3.5 rounded-xl shadow-2xl border backdrop-blur-sm transition-all duration-300 ${
        type === "success"
          ? "bg-green-500/15 border-green-500/30 text-green-400"
          : "bg-red-500/15 border-red-500/30 text-red-400"
      }`}
    >
      {type === "success" ? <CheckCircle size={18} /> : <AlertCircle size={18} />}
      <span className="text-[13px] font-medium">{message}</span>
      <button onClick={onClose} className="ml-2 opacity-60 hover:opacity-100">
        <X size={14} />
      </button>
    </div>
  );
}

function PasswordField({ label, value, onChange, placeholder }) {
  const [show, setShow] = useState(false);
  return (
    <div>
      <label className="block text-[12px] font-semibold text-text-dim uppercase tracking-wider mb-1.5">
        {label}
      </label>
      <div className="relative">
        <input
          type={show ? "text" : "password"}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          className="w-full px-3 py-2.5 pr-10 bg-secondary border border-border rounded-lg text-[13px] text-foreground placeholder:text-text-dim focus:border-primary focus:ring-1 focus:ring-primary/30 outline-none transition-colors"
        />
        <button
          type="button"
          onClick={() => setShow(!show)}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-text-dim hover:text-foreground transition-colors"
        >
          {show ? <EyeOff size={15} /> : <Eye size={15} />}
        </button>
      </div>
    </div>
  );
}

function StrengthBar({ password }) {
  const strength = (() => {
    if (!password) return 0;
    let s = 0;
    if (password.length >= 8) s++;
    if (/[A-Z]/.test(password)) s++;
    if (/[0-9]/.test(password)) s++;
    if (/[^A-Za-z0-9]/.test(password)) s++;
    return s;
  })();
  const labels = ["", "Faible", "Moyen", "Fort", "Très fort"];
  const colors = ["", "bg-red-500", "bg-orange-500", "bg-yellow-500", "bg-green-500"];
  const textColors = ["", "text-red-400", "text-orange-400", "text-yellow-400", "text-green-400"];
  return password ? (
    <div className="mt-2">
      <div className="flex gap-1">
        {[1, 2, 3, 4].map((i) => (
          <div
            key={i}
            className={`h-1 flex-1 rounded-full transition-colors duration-300 ${
              i <= strength ? colors[strength] : "bg-border"
            }`}
          />
        ))}
      </div>
      <p className={`text-[11px] mt-1 ${textColors[strength]}`}>{labels[strength]}</p>
    </div>
  ) : null;
}

function RoleBadge({ role }) {
  const colors = {
    Administrateur: "bg-red-500/15 border-red-500/25 text-red-400",
    Manager: "bg-blue-500/15 border-blue-500/25 text-blue-400",
    Analyste: "bg-violet-500/15 border-violet-500/25 text-violet-400",
    Consultant: "bg-orange-500/15 border-orange-500/25 text-orange-400",
    Auditeur: "bg-teal-500/15 border-teal-500/25 text-teal-400",
  };
  return (
    <span className={`px-2.5 py-0.5 rounded-full border text-[11px] font-semibold ${colors[role] || "bg-primary/15 border-primary/25 text-primary"}`}>
      {role}
    </span>
  );
}

function ProfilPage() {
  const { user, updateProfile, changePassword, logout, hasPermission } = useAuth();
  const navigate = useNavigate();

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(null);
  const [toast, setToast] = useState(null);
  const [activeTab, setActiveTab] = useState("info");
  const [avatarPreview, setAvatarPreview] = useState(null);
  const [pwLoading, setPwLoading] = useState(false);

  // Password state
  const [pwForm, setPwForm] = useState({ current: "", nouveau: "", confirm: "" });
  const [pwError, setPwError] = useState("");

  const fileRef = useRef(null);

  if (!user) return null;

  const showToast = (message, type = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3500);
  };

  const handleEdit = () => {
    setDraft({ ...user });
    setEditing(true);
  };

  const handleCancel = () => {
    setEditing(false);
    setDraft(null);
    setAvatarPreview(null);
  };

  const handleSave = () => {
    if (!draft.prenom?.trim() || !draft.nom?.trim() || !draft.email?.trim()) {
      showToast("Prénom, nom et email sont obligatoires", "error");
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(draft.email)) {
      showToast("Adresse email invalide", "error");
      return;
    }
    updateProfile({ ...draft, avatar: avatarPreview ?? user.avatar });
    setEditing(false);
    setDraft(null);
    setAvatarPreview(null);
    showToast("Profil mis à jour avec succès");
  };

  const handleAvatarChange = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 2 * 1024 * 1024) {
      showToast("Image trop grande (max 2 Mo)", "error");
      return;
    }
    const reader = new FileReader();
    reader.onload = () => setAvatarPreview(reader.result);
    reader.readAsDataURL(file);
  };

  const handlePasswordChange = async () => {
    setPwError("");
    if (!pwForm.current) {
      setPwError("Mot de passe actuel requis");
      return;
    }
    if (pwForm.nouveau.length < 8) {
      setPwError("Le nouveau mot de passe doit avoir au moins 8 caractères");
      return;
    }
    if (!/[A-Z]/.test(pwForm.nouveau)) {
      setPwError("Le mot de passe doit contenir au moins une majuscule");
      return;
    }
    if (!/[0-9]/.test(pwForm.nouveau)) {
      setPwError("Le mot de passe doit contenir au moins un chiffre");
      return;
    }
    if (pwForm.nouveau !== pwForm.confirm) {
      setPwError("Les mots de passe ne correspondent pas");
      return;
    }

    setPwLoading(true);
    const result = await changePassword(pwForm.current, pwForm.nouveau);
    setPwLoading(false);

    if (result.success) {
      setPwForm({ current: "", nouveau: "", confirm: "" });
      showToast("Mot de passe modifié avec succès");
    } else {
      setPwError(result.error);
    }
  };

  const handleLogout = () => {
    logout();
    navigate({ to: "/login" });
  };

  const currentData = editing ? draft : user;
  const currentAvatar = editing ? (avatarPreview ?? user.avatar) : user.avatar;
  const permissions = ROLE_PERMISSIONS[user.role] || {};

  const field = (key, label, icon, type = "text", options = null) => {
    const Icon = icon;
    const val = currentData?.[key] ?? "";
    // Only admins can change roles
    const readOnly = key === "role" && !hasPermission("canEditUsers");

    return (
      <div>
        <label className="flex items-center gap-1.5 text-[11px] font-semibold text-text-dim uppercase tracking-wider mb-1.5">
          <Icon size={11} />
          {label}
        </label>
        {editing && !readOnly ? (
          options ? (
            <select
              value={val}
              onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
              className="w-full px-3 py-2.5 bg-secondary border border-border rounded-lg text-[13px] text-foreground focus:border-primary focus:ring-1 focus:ring-primary/30 outline-none transition-colors"
            >
              {options.map((o) => (
                <option key={o} value={o} className="bg-background">
                  {o}
                </option>
              ))}
            </select>
          ) : (
            <input
              type={type}
              value={val}
              onChange={(e) => setDraft({ ...draft, [key]: e.target.value })}
              className="w-full px-3 py-2.5 bg-secondary border border-border rounded-lg text-[13px] text-foreground focus:border-primary focus:ring-1 focus:ring-primary/30 outline-none transition-colors"
            />
          )
        ) : (
          <div className="flex items-center gap-2">
            {key === "role" ? (
              <RoleBadge role={val} />
            ) : (
              <p className="px-3 py-2.5 bg-surface/50 border border-border/50 rounded-lg text-[13px] text-foreground flex-1">
                {val || <span className="text-text-dim italic">Non renseigné</span>}
              </p>
            )}
            {key === "role" && readOnly && (
              <span className="text-[10px] text-text-dim">(non modifiable)</span>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="max-w-4xl space-y-6">
      {toast && (
        <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />
      )}

      {/* Header card */}
      <div className="bg-gradient-to-br from-card via-card/98 to-card/95 border border-border/60 rounded-2xl p-6 flex items-start gap-6 flex-wrap">
        {/* Avatar */}
        <div className="relative flex-shrink-0">
          <div className="w-24 h-24 rounded-2xl border-2 border-primary/30 overflow-hidden bg-primary/10 flex items-center justify-center">
            {currentAvatar ? (
              <img src={currentAvatar} alt="Avatar" className="w-full h-full object-cover" />
            ) : (
              <span className="text-3xl font-bold text-primary">{user.initiales}</span>
            )}
          </div>
          {editing && (
            <div className="absolute -bottom-2 -right-2 flex gap-1">
              <button
                onClick={() => fileRef.current?.click()}
                className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center shadow-lg hover:bg-primary/90 transition-colors"
              >
                <Camera size={13} className="text-white" />
              </button>
              {currentAvatar && (
                <button
                  onClick={() => setAvatarPreview(null)}
                  className="w-7 h-7 rounded-lg bg-red-500/80 flex items-center justify-center shadow-lg hover:bg-red-500 transition-colors"
                >
                  <Trash2 size={11} className="text-white" />
                </button>
              )}
            </div>
          )}
          <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleAvatarChange} />
        </div>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold text-foreground">
            {user.prenom} {user.nom}
          </h1>
          <p className="text-[13px] text-text-dim mt-0.5">
            {user.poste} · {user.departement}
          </p>
          <div className="flex items-center gap-2 mt-2 flex-wrap">
            <RoleBadge role={user.role} />
            <span className="text-[12px] text-text-dim flex items-center gap-1">
              <MapPin size={11} />
              {user.localisation}
            </span>
          </div>
          {user.bio && (
            <p className="text-[12px] text-text-dim mt-3 max-w-lg leading-relaxed">{user.bio}</p>
          )}
        </div>

        {/* Actions */}
        <div className="flex items-start gap-2 flex-shrink-0 flex-wrap">
          {editing ? (
            <>
              <button
                onClick={handleCancel}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-border text-[12px] font-medium text-foreground hover:bg-surface-hover transition-colors"
              >
                <X size={14} />
                Annuler
              </button>
              <button
                onClick={handleSave}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-primary text-white text-[12px] font-medium hover:bg-primary/90 transition-colors shadow-md shadow-primary/25"
              >
                <Save size={14} />
                Enregistrer
              </button>
            </>
          ) : (
            <>
              <button
                onClick={handleEdit}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-primary/30 bg-primary/10 text-primary text-[12px] font-medium hover:bg-primary/20 transition-colors"
              >
                <Edit3 size={14} />
                Modifier
              </button>
              <button
                onClick={handleLogout}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-border text-[12px] font-medium text-text-dim hover:text-red-400 hover:border-red-500/30 hover:bg-red-500/5 transition-colors"
              >
                <LogOut size={14} />
                Déconnexion
              </button>
            </>
          )}
        </div>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 p-1 bg-secondary/50 rounded-xl border border-border/50 w-fit">
        {[
          { id: "info", label: "Informations" },
          { id: "securite", label: "Sécurité" },
          { id: "permissions", label: "Permissions" },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`px-4 py-2 rounded-lg text-[12px] font-semibold transition-all duration-200 ${
              activeTab === tab.id
                ? "bg-primary text-white shadow-md shadow-primary/25"
                : "text-text-dim hover:text-foreground"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ── Tab: Info ── */}
      {activeTab === "info" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-gradient-to-br from-card to-card/95 border border-border/60 rounded-2xl p-5 space-y-4">
            <h2 className="text-[13px] font-bold text-foreground uppercase tracking-wider flex items-center gap-2">
              <User size={14} className="text-primary" />
              Informations personnelles
            </h2>
            {field("prenom", "Prénom", User)}
            {field("nom", "Nom", User)}
            {field("email", "Email", Mail, "email")}
            {field("telephone", "Téléphone", Phone, "tel")}
            {field("localisation", "Localisation", MapPin)}
            <div>
              <label className="flex items-center gap-1.5 text-[11px] font-semibold text-text-dim uppercase tracking-wider mb-1.5">
                <Edit3 size={11} />
                Bio
              </label>
              {editing ? (
                <textarea
                  value={draft?.bio ?? ""}
                  onChange={(e) => setDraft({ ...draft, bio: e.target.value })}
                  rows={3}
                  className="w-full px-3 py-2.5 bg-secondary border border-border rounded-lg text-[13px] text-foreground focus:border-primary focus:ring-1 focus:ring-primary/30 outline-none transition-colors resize-none"
                />
              ) : (
                <p className="px-3 py-2.5 bg-surface/50 border border-border/50 rounded-lg text-[13px] text-foreground min-h-[70px] leading-relaxed">
                  {user.bio || <span className="text-text-dim italic">Non renseigné</span>}
                </p>
              )}
            </div>
          </div>

          <div className="bg-gradient-to-br from-card to-card/95 border border-border/60 rounded-2xl p-5 space-y-4">
            <h2 className="text-[13px] font-bold text-foreground uppercase tracking-wider flex items-center gap-2">
              <Building2 size={14} className="text-primary" />
              Informations professionnelles
            </h2>
            {field("poste", "Poste", Building2)}
            {field("departement", "Département", Building2, "text", DEPARTMENTS)}
            {field("role", "Rôle système", Lock, "text", hasPermission("canEditUsers") ? ROLES : null)}

            <div className="mt-4 pt-4 border-t border-border/50">
              <p className="text-[11px] font-semibold text-text-dim uppercase tracking-wider mb-3">
                Activité récente
              </p>
              {[
                { label: "Dernière connexion", value: "Aujourd'hui, 09:14" },
                { label: "Sessions actives", value: "1 session" },
                { label: "Compte créé", value: "15 Jan 2024" },
              ].map((item) => (
                <div
                  key={item.label}
                  className="flex justify-between items-center py-1.5 border-b border-border/30 last:border-0"
                >
                  <span className="text-[12px] text-text-dim">{item.label}</span>
                  <span className="text-[12px] text-foreground font-medium">{item.value}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── Tab: Sécurité ── */}
      {activeTab === "securite" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-gradient-to-br from-card to-card/95 border border-border/60 rounded-2xl p-5 space-y-4">
            <h2 className="text-[13px] font-bold text-foreground uppercase tracking-wider flex items-center gap-2">
              <Lock size={14} className="text-primary" />
              Changer le mot de passe
            </h2>

            {pwError && (
              <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg bg-red-500/10 border border-red-500/20 text-red-400 text-[12px]">
                <AlertCircle size={14} className="flex-shrink-0" />
                {pwError}
              </div>
            )}

            <PasswordField
              label="Mot de passe actuel"
              value={pwForm.current}
              onChange={(v) => { setPwForm({ ...pwForm, current: v }); setPwError(""); }}
              placeholder="••••••••"
            />
            <PasswordField
              label="Nouveau mot de passe"
              value={pwForm.nouveau}
              onChange={(v) => { setPwForm({ ...pwForm, nouveau: v }); setPwError(""); }}
              placeholder="Min. 8 car., 1 maj., 1 chiffre"
            />
            <StrengthBar password={pwForm.nouveau} />
            <PasswordField
              label="Confirmer le mot de passe"
              value={pwForm.confirm}
              onChange={(v) => { setPwForm({ ...pwForm, confirm: v }); setPwError(""); }}
              placeholder="Répétez le mot de passe"
            />

            <button
              onClick={handlePasswordChange}
              disabled={pwLoading}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg bg-primary text-white text-[13px] font-semibold hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors shadow-md shadow-primary/25 mt-2"
            >
              {pwLoading ? (
                <span className="animate-pulse">Mise à jour…</span>
              ) : (
                <>
                  <Lock size={14} />
                  Mettre à jour le mot de passe
                </>
              )}
            </button>

            <div className="pt-2 border-t border-border/50">
              <p className="text-[11px] text-text-dim font-semibold uppercase tracking-wider mb-2">
                Règles
              </p>
              {[
                "Minimum 8 caractères",
                "Au moins une lettre majuscule",
                "Au moins un chiffre",
              ].map((r) => (
                <p key={r} className="text-[11px] text-text-dim flex items-center gap-1.5 mb-1">
                  <span className="w-1 h-1 rounded-full bg-text-dim" />
                  {r}
                </p>
              ))}
            </div>
          </div>

          <div className="bg-gradient-to-br from-card to-card/95 border border-border/60 rounded-2xl p-5 space-y-4">
            <h2 className="text-[13px] font-bold text-foreground uppercase tracking-wider flex items-center gap-2">
              <CheckCircle size={14} className="text-primary" />
              Sécurité du compte
            </h2>
            {[
              { label: "Authentification 2FA", status: "Désactivée", color: "text-orange-400", bg: "bg-orange-500/10 border-orange-500/20" },
              { label: "Connexions suspectes", status: "Aucune détectée", color: "text-green-400", bg: "bg-green-500/10 border-green-500/20" },
              { label: "Niveau de sécurité", status: "Moyen", color: "text-yellow-400", bg: "bg-yellow-500/10 border-yellow-500/20" },
            ].map((item) => (
              <div key={item.label} className={`flex items-center justify-between px-3 py-2.5 rounded-lg border ${item.bg}`}>
                <span className="text-[12px] text-foreground">{item.label}</span>
                <span className={`text-[11px] font-semibold ${item.color}`}>{item.status}</span>
              </div>
            ))}

            <div className="mt-2 pt-4 border-t border-border/50">
              <p className="text-[11px] font-semibold text-text-dim uppercase tracking-wider mb-3">
                Session active
              </p>
              <div className="flex items-center justify-between p-3 bg-surface/50 rounded-lg border border-border/50">
                <div>
                  <p className="text-[12px] font-medium text-foreground">Chrome · Windows 11</p>
                  <p className="text-[11px] text-text-dim">Tunis, Tunisie · Maintenant</p>
                </div>
                <span className="w-2 h-2 rounded-full bg-green-500 animate-pulse" />
              </div>
            </div>

            <button
              onClick={handleLogout}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-lg border border-red-500/30 bg-red-500/10 text-red-400 text-[12px] font-semibold hover:bg-red-500/20 transition-colors"
            >
              <LogOut size={13} />
              Déconnexion
            </button>
          </div>
        </div>
      )}

      {/* ── Tab: Permissions ── */}
      {activeTab === "permissions" && (
        <div className="bg-gradient-to-br from-card to-card/95 border border-border/60 rounded-2xl p-5">
          <h2 className="text-[13px] font-bold text-foreground uppercase tracking-wider flex items-center gap-2 mb-5">
            <Shield size={14} className="text-primary" />
            Permissions du rôle — <RoleBadge role={user.role} />
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Capabilities */}
            <div>
              <p className="text-[11px] font-semibold text-text-dim uppercase tracking-wider mb-3">
                Capacités
              </p>
              <div className="space-y-2">
                {[
                  { key: "canViewAll", label: "Accès à tous les modules" },
                  { key: "canEditUsers", label: "Gestion des utilisateurs" },
                  { key: "canExport", label: "Export des données" },
                  { key: "canChangeSettings", label: "Modification des paramètres" },
                ].map((p) => (
                  <div key={p.key} className="flex items-center justify-between py-2 border-b border-border/30 last:border-0">
                    <span className="text-[12px] text-foreground">{p.label}</span>
                    {permissions[p.key] ? (
                      <span className="flex items-center gap-1 text-[11px] font-semibold text-green-400">
                        <CheckCircle size={12} /> Autorisé
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-[11px] font-semibold text-text-dim">
                        <X size={12} /> Refusé
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            {/* Accessible routes */}
            <div>
              <p className="text-[11px] font-semibold text-text-dim uppercase tracking-wider mb-3">
                Pages accessibles
              </p>
              <div className="space-y-1.5">
                {permissions.routes?.includes("*") ? (
                  <p className="text-[12px] text-green-400 font-medium flex items-center gap-1.5">
                    <CheckCircle size={13} /> Accès complet à toutes les pages
                  </p>
                ) : (
                  permissions.routes?.map((route) => (
                    <div key={route} className="flex items-center gap-2 text-[12px] text-foreground">
                      <span className="w-1.5 h-1.5 rounded-full bg-primary flex-shrink-0" />
                      <span className="font-mono text-[11px] bg-secondary px-2 py-0.5 rounded">{route}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
