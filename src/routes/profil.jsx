import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useRef, useState } from "react";
import {
  AlertCircle,
  Building2,
  Camera,
  CheckCircle,
  Edit3,
  LogOut,
  Mail,
  MapPin,
  Phone,
  Save,
  Shield,
  Trash2,
  User,
  X,
} from "lucide-react";
import { ENTRY_ROLES, ROLE_PERMISSIONS, useAuth } from "@/store/useAuth";

export const Route = createFileRoute("/profil")({
  component: ProfilPage,
});

const ROLES = ENTRY_ROLES.map((profile) => profile.role);
const DEPARTMENTS = ["Finance", "Commercial", "Logistique", "IT", "Direction", "Comptabilite"];

function Toast({ message, type, onClose }) {
  return (
    <div
      className={`fixed bottom-6 right-6 z-50 flex items-center gap-3 px-5 py-3.5 rounded-lg shadow-2xl border backdrop-blur-sm transition-all duration-300 ${
        type === "success"
          ? "bg-green-500/15 border-green-500/30 text-green-400"
          : "bg-red-500/15 border-red-500/30 text-red-400"
      }`}
    >
      {type === "success" ? <CheckCircle size={18} /> : <AlertCircle size={18} />}
      <span className="text-[13px] font-medium">{message}</span>
      <button type="button" onClick={onClose} className="ml-2 opacity-60 hover:opacity-100">
        <X size={14} />
      </button>
    </div>
  );
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
    <span
      className={`px-2.5 py-0.5 rounded-full border text-[11px] font-semibold ${colors[role] || "bg-primary/15 border-primary/25 text-primary"}`}
    >
      {role}
    </span>
  );
}

function ProfilPage() {
  const { user, updateProfile, logout } = useAuth();
  const navigate = useNavigate();
  const fileRef = useRef(null);

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(null);
  const [toast, setToast] = useState(null);
  const [activeTab, setActiveTab] = useState("info");
  const [avatarPreview, setAvatarPreview] = useState(null);

  if (!user) return null;

  const showToast = (message, type = "success") => {
    setToast({ message, type });
    setTimeout(() => setToast(null), 3500);
  };

  const currentData = editing ? draft : user;
  const currentAvatar = editing ? (avatarPreview ?? user.avatar) : user.avatar;
  const permissions = ROLE_PERMISSIONS[user.role] || {};

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
      showToast("Prenom, nom et email sont obligatoires", "error");
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
    showToast("Profil mis a jour");
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

  const handleReturnHome = () => {
    logout();
    navigate({ to: "/login" });
  };

  const field = (key, label, icon, type = "text", options = null) => {
    const Icon = icon;
    const val = currentData?.[key] ?? "";

    return (
      <div>
        <label className="flex items-center gap-1.5 text-[11px] font-semibold text-text-dim uppercase tracking-wider mb-1.5">
          <Icon size={11} />
          {label}
        </label>
        {editing ? (
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
                {val || <span className="text-text-dim italic">Non renseigne</span>}
              </p>
            )}
          </div>
        )}
      </div>
    );
  };

  return (
    <div className="max-w-4xl space-y-6">
      {toast && <Toast message={toast.message} type={toast.type} onClose={() => setToast(null)} />}

      <div className="bg-gradient-to-br from-card via-card/98 to-card/95 border border-border/60 rounded-2xl p-6 flex items-start gap-6 flex-wrap">
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
                type="button"
                onClick={() => fileRef.current?.click()}
                className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center shadow-lg hover:bg-primary/90 transition-colors"
                title="Photo"
              >
                <Camera size={13} className="text-white" />
              </button>
              {currentAvatar && (
                <button
                  type="button"
                  onClick={() => setAvatarPreview(null)}
                  className="w-7 h-7 rounded-lg bg-red-500/80 flex items-center justify-center shadow-lg hover:bg-red-500 transition-colors"
                  title="Supprimer la photo"
                >
                  <Trash2 size={11} className="text-white" />
                </button>
              )}
            </div>
          )}
          <input
            ref={fileRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={handleAvatarChange}
          />
        </div>

        <div className="flex-1 min-w-0">
          <h1 className="text-2xl font-bold text-foreground">
            {user.prenom} {user.nom}
          </h1>
          <p className="text-[13px] text-text-dim mt-0.5">
            {user.poste} - {user.departement}
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

        <div className="flex items-start gap-2 flex-shrink-0 flex-wrap">
          {editing ? (
            <>
              <button
                type="button"
                onClick={handleCancel}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-border text-[12px] font-medium text-foreground hover:bg-surface-hover transition-colors"
              >
                <X size={14} />
                Annuler
              </button>
              <button
                type="button"
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
                type="button"
                onClick={handleEdit}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-primary/30 bg-primary/10 text-primary text-[12px] font-medium hover:bg-primary/20 transition-colors"
              >
                <Edit3 size={14} />
                Modifier
              </button>
              <button
                type="button"
                onClick={handleReturnHome}
                className="flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-border text-[12px] font-medium text-text-dim hover:text-primary hover:border-primary/30 hover:bg-primary/5 transition-colors"
              >
                <LogOut size={14} />
                Changer de role
              </button>
            </>
          )}
        </div>
      </div>

      <div className="flex gap-1 p-1 bg-secondary/50 rounded-xl border border-border/50 w-fit">
        {[
          { id: "info", label: "Informations" },
          { id: "permissions", label: "Permissions" },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
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

      {activeTab === "info" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="bg-gradient-to-br from-card to-card/95 border border-border/60 rounded-2xl p-5 space-y-4">
            <h2 className="text-[13px] font-bold text-foreground uppercase tracking-wider flex items-center gap-2">
              <User size={14} className="text-primary" />
              Informations personnelles
            </h2>
            {field("prenom", "Prenom", User)}
            {field("nom", "Nom", User)}
            {field("email", "Email", Mail, "email")}
            {field("telephone", "Telephone", Phone, "tel")}
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
                  {user.bio || <span className="text-text-dim italic">Non renseigne</span>}
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
            {field("departement", "Departement", Building2, "text", DEPARTMENTS)}
            {field("role", "Role systeme", Shield, "text", ROLES)}

            <div className="mt-4 pt-4 border-t border-border/50">
              <p className="text-[11px] font-semibold text-text-dim uppercase tracking-wider mb-3">
                Session
              </p>
              {[
                { label: "Mode d'entree", value: "Bouton sans mot de passe" },
                { label: "Role actif", value: user.role },
                { label: "Pages accessibles", value: permissions.routes?.includes("*") ? "Toutes" : `${permissions.routes?.length || 0}` },
              ].map((item) => (
                <div
                  key={item.label}
                  className="flex justify-between items-center py-1.5 border-b border-border/30 last:border-0 gap-3"
                >
                  <span className="text-[12px] text-text-dim">{item.label}</span>
                  <span className="text-[12px] text-foreground font-medium text-right">
                    {item.value}
                  </span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {activeTab === "permissions" && (
        <div className="bg-gradient-to-br from-card to-card/95 border border-border/60 rounded-2xl p-5">
          <h2 className="text-[13px] font-bold text-foreground uppercase tracking-wider flex items-center gap-2 mb-5">
            <Shield size={14} className="text-primary" />
            Permissions du role <RoleBadge role={user.role} />
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <div>
              <p className="text-[11px] font-semibold text-text-dim uppercase tracking-wider mb-3">
                Capacites
              </p>
              <div className="space-y-2">
                {[
                  { key: "canViewAll", label: "Acces a tous les modules" },
                  { key: "canEditUsers", label: "Gestion des utilisateurs" },
                  { key: "canExport", label: "Export des donnees" },
                  { key: "canChangeSettings", label: "Modification des parametres" },
                ].map((p) => (
                  <div
                    key={p.key}
                    className="flex items-center justify-between py-2 border-b border-border/30 last:border-0 gap-3"
                  >
                    <span className="text-[12px] text-foreground">{p.label}</span>
                    {permissions[p.key] ? (
                      <span className="flex items-center gap-1 text-[11px] font-semibold text-green-400">
                        <CheckCircle size={12} /> Autorise
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-[11px] font-semibold text-text-dim">
                        <X size={12} /> Refuse
                      </span>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div>
              <p className="text-[11px] font-semibold text-text-dim uppercase tracking-wider mb-3">
                Pages accessibles
              </p>
              <div className="space-y-1.5">
                {permissions.routes?.includes("*") ? (
                  <p className="text-[12px] text-green-400 font-medium flex items-center gap-1.5">
                    <CheckCircle size={13} /> Acces complet a toutes les pages
                  </p>
                ) : (
                  permissions.routes?.map((route) => (
                    <div
                      key={route}
                      className="flex items-center gap-2 text-[12px] text-foreground"
                    >
                      <span className="w-1.5 h-1.5 rounded-full bg-primary flex-shrink-0" />
                      <span className="font-mono text-[11px] bg-secondary px-2 py-0.5 rounded">
                        {route}
                      </span>
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
