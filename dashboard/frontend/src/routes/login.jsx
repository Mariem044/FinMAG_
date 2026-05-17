import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect, useMemo, useState } from "react";
import { ArrowRight, BarChart2, CheckCircle2, Loader2, ShieldCheck } from "lucide-react";
import { ENTRY_ROLES, ROLE_PERMISSIONS, useAuth } from "@/store/useAuth";

export const Route = createFileRoute("/login")({
  component: LoginPage,
});

const roleStyles = {
  Administrateur: "border-red-500/40 bg-red-500/10 text-red-300",
  Manager: "border-blue-500/40 bg-blue-500/10 text-blue-300",
  Analyste: "border-violet-500/40 bg-violet-500/10 text-violet-300",
  Consultant: "border-orange-500/40 bg-orange-500/10 text-orange-300",
  Auditeur: "border-teal-500/40 bg-teal-500/10 text-teal-300",
};

const roleDescriptions = {
  Administrateur: "Acces complet",
  Manager: "Pilotage operationnel",
  Analyste: "Analyse et exports",
  Consultant: "Consultation limitee",
  Auditeur: "Controle fiscal et bancaire",
};

function LoginPage() {
  const navigate = useNavigate();
  const { enterAsRole, isAuthenticated, isLoading } = useAuth();
  const [selectedRole, setSelectedRole] = useState("Administrateur");

  const selectedProfile = useMemo(
    () => ENTRY_ROLES.find((profile) => profile.role === selectedRole) || ENTRY_ROLES[0],
    [selectedRole],
  );

  useEffect(() => {
    if (isAuthenticated) {
      navigate({ to: "/" });
    }
  }, [isAuthenticated, navigate]);

  const handleEnter = async () => {
    const success = await enterAsRole(selectedRole);
    if (success) navigate({ to: "/" });
  };

  const routeCount = ROLE_PERMISSIONS[selectedRole]?.routes?.includes("*")
    ? "Toutes les pages"
    : `${ROLE_PERMISSIONS[selectedRole]?.routes?.length || 0} pages`;

  return (
    <div className="min-h-screen bg-background flex">
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-[#0d1117] via-[#111826] to-[#0a0f1a] relative overflow-hidden flex-col justify-between p-12">
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage: `linear-gradient(#4f8dfd 1px, transparent 1px), linear-gradient(90deg, #4f8dfd 1px, transparent 1px)`,
            backgroundSize: "48px 48px",
          }}
        />

        <div className="relative z-10">
          <div className="flex items-center gap-3 mb-2">
            <div className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center shadow-lg shadow-primary/40">
              <BarChart2 size={20} className="text-white" />
            </div>
            <span className="text-2xl font-extrabold text-white tracking-tight">FinMAG</span>
          </div>
          <p className="text-[11px] text-text-dim font-semibold tracking-[0.2em] uppercase">
            MAG Distribution Analytics
          </p>
        </div>

        <div className="relative z-10 space-y-6">
          <h1 className="text-4xl font-bold text-white leading-tight">
            Accueil
            <br />
            <span className="text-primary">FinMAG</span>
          </h1>
          <p className="text-text-muted text-[15px] leading-relaxed max-w-sm">
            Entrez directement dans le tableau de bord et gardez les vues adaptees au role choisi.
          </p>

          <div className="grid grid-cols-3 gap-4 pt-4">
            {[
              { value: "38", label: "Indicateurs" },
              { value: "12", label: "Modules" },
              { value: "5", label: "Roles" },
            ].map((s) => (
              <div
                key={s.label}
                className="bg-white/[0.04] border border-white/[0.08] rounded-lg p-4 text-center"
              >
                <p className="text-2xl font-bold text-primary">{s.value}</p>
                <p className="text-[11px] text-text-dim mt-1">{s.label}</p>
              </div>
            ))}
          </div>
        </div>

        <div className="relative z-10">
          <p className="text-[11px] text-text-dim">MAG Distribution - v2.0.0</p>
        </div>
      </div>

      <div className="flex-1 flex flex-col items-center justify-center px-6 py-12 bg-background">
        <div className="lg:hidden flex items-center gap-2 mb-10">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
            <BarChart2 size={16} className="text-white" />
          </div>
          <span className="text-xl font-extrabold text-foreground">FinMAG</span>
        </div>

        <div className="w-full max-w-xl">
          <div className="mb-8">
            <div className="inline-flex items-center gap-2 rounded-full border border-primary/25 bg-primary/10 px-3 py-1 text-[11px] font-semibold text-primary mb-4">
              <ShieldCheck size={13} />
              Entree sans mot de passe
            </div>
            <h2 className="text-2xl font-bold text-foreground">Choisir un role</h2>
            <p className="text-text-dim text-[13px] mt-1">
              Selectionnez le profil de travail puis entrez dans l'application.
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            {ENTRY_ROLES.map((profile) => {
              const active = selectedRole === profile.role;
              return (
                <button
                  key={profile.role}
                  type="button"
                  onClick={() => setSelectedRole(profile.role)}
                  className={`text-left rounded-lg border px-4 py-3 transition-all duration-150 ${
                    active
                      ? `${roleStyles[profile.role]} shadow-lg shadow-black/20`
                      : "border-border/70 bg-secondary/50 text-foreground hover:border-primary/40 hover:bg-primary/5"
                  }`}
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <p className="text-[13px] font-semibold truncate">{profile.role}</p>
                      <p className="text-[11px] text-text-dim mt-1">
                        {roleDescriptions[profile.role]}
                      </p>
                    </div>
                    {active && <CheckCircle2 size={16} className="flex-shrink-0" />}
                  </div>
                  <p className="text-[11px] text-text-dim mt-3 truncate">
                    {profile.prenom} {profile.nom}
                  </p>
                </button>
              );
            })}
          </div>

          <div className="mt-5 rounded-lg border border-border/70 bg-card/80 px-4 py-3">
            <div className="flex items-center justify-between gap-4">
              <div className="min-w-0">
                <p className="text-[13px] font-semibold text-foreground truncate">
                  {selectedProfile.prenom} {selectedProfile.nom}
                </p>
                <p className="text-[11px] text-text-dim truncate">
                  {selectedProfile.poste} - {routeCount}
                </p>
              </div>
              <span
                className={`px-2.5 py-1 rounded-full border text-[11px] font-semibold whitespace-nowrap ${roleStyles[selectedRole]}`}
              >
                {selectedRole}
              </span>
            </div>
          </div>

          <button
            type="button"
            onClick={handleEnter}
            disabled={isLoading}
            className="mt-5 w-full flex items-center justify-center gap-2 py-3 rounded-lg bg-primary text-white text-[13px] font-semibold hover:bg-primary/90 disabled:opacity-60 disabled:cursor-not-allowed transition-all duration-200 shadow-lg shadow-primary/30 hover:shadow-primary/50 hover:scale-[1.01] active:scale-[0.99]"
          >
            {isLoading ? (
              <>
                <Loader2 size={15} className="animate-spin" />
                Entree en cours...
              </>
            ) : (
              <>
                Entrer
                <ArrowRight size={15} />
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
