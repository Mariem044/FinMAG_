import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useState, useEffect } from "react";
import { Eye, EyeOff, AlertCircle, Loader2, BarChart2 } from "lucide-react";
import { useAuth } from "@/store/useAuth";

export const Route = createFileRoute("/login")({
  component: LoginPage,
});

const DEMO_ACCOUNTS = [
  { email: "ahmed.dridi@magdistribution.tn", password: "Admin@2024", role: "Administrateur" },
  { email: "sarra.bensalah@magdistribution.tn", password: "Manager@2024", role: "Manager" },
  { email: "karim.maaloul@magdistribution.tn", password: "Analyste@2024", role: "Analyste" },
];

function LoginPage() {
  const navigate = useNavigate();
  const { login, isAuthenticated, loginError, isLoading, clearError } = useAuth();

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [touched, setTouched] = useState({ email: false, password: false });

  // Redirect if already authenticated
  useEffect(() => {
    if (isAuthenticated) {
      navigate({ to: "/" });
    }
  }, [isAuthenticated, navigate]);

  // Clear error when user types
  useEffect(() => {
    if (loginError) clearError();
  }, [email, password]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setTouched({ email: true, password: true });
    if (!email || !password) return;
    const success = await login(email, password);
    if (success) navigate({ to: "/" });
  };

  const fillDemo = (account) => {
    setEmail(account.email);
    setPassword(account.password);
    clearError();
  };

  const emailError = touched.email && !email ? "Email requis" : "";
  const passwordError = touched.password && !password ? "Mot de passe requis" : "";

  return (
    <div className="min-h-screen bg-background flex">
      {/* Left panel — branding */}
      <div className="hidden lg:flex lg:w-1/2 bg-gradient-to-br from-[#0d1117] via-[#111826] to-[#0a0f1a] relative overflow-hidden flex-col justify-between p-12">
        {/* Background grid */}
        <div
          className="absolute inset-0 opacity-[0.04]"
          style={{
            backgroundImage: `linear-gradient(#4f8dfd 1px, transparent 1px), linear-gradient(90deg, #4f8dfd 1px, transparent 1px)`,
            backgroundSize: "48px 48px",
          }}
        />
        {/* Glow */}
        <div className="absolute top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[500px] h-[500px] bg-primary/10 rounded-full blur-3xl pointer-events-none" />

        {/* Logo */}
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

        {/* Center content */}
        <div className="relative z-10 space-y-6">
          <h1 className="text-4xl font-bold text-white leading-tight">
            Pilotez votre<br />
            <span className="text-primary">performance</span><br />
            en temps réel.
          </h1>
          <p className="text-text-muted text-[15px] leading-relaxed max-w-sm">
            Tableau de bord financier complet pour MAG Distribution — CA, trésorerie, stocks, acteurs et comptabilité.
          </p>

          {/* Stats */}
          <div className="grid grid-cols-3 gap-4 pt-4">
            {[
              { value: "38", label: "KPIs" },
              { value: "12", label: "Modules" },
              { value: "5", label: "Exercices" },
            ].map((s) => (
              <div key={s.label} className="bg-white/[0.04] border border-white/[0.08] rounded-xl p-4 text-center">
                <p className="text-2xl font-bold text-primary">{s.value}</p>
                <p className="text-[11px] text-text-dim mt-1">{s.label}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Footer */}
        <div className="relative z-10">
          <p className="text-[11px] text-text-dim">© 2024 MAG Distribution · v2.0.0</p>
        </div>
      </div>

      {/* Right panel — login form */}
      <div className="flex-1 flex flex-col items-center justify-center px-6 py-12 bg-background">
        {/* Mobile logo */}
        <div className="lg:hidden flex items-center gap-2 mb-10">
          <div className="w-8 h-8 rounded-lg bg-primary flex items-center justify-center">
            <BarChart2 size={16} className="text-white" />
          </div>
          <span className="text-xl font-extrabold text-foreground">FinMAG</span>
        </div>

        <div className="w-full max-w-sm">
          <div className="mb-8">
            <h2 className="text-2xl font-bold text-foreground">Connexion</h2>
            <p className="text-text-dim text-[13px] mt-1">Accédez à votre tableau de bord</p>
          </div>

          {/* Error banner */}
          {loginError && (
            <div className="flex items-center gap-3 px-4 py-3 rounded-xl bg-red-500/10 border border-red-500/30 text-red-400 text-[13px] mb-5">
              <AlertCircle size={16} className="flex-shrink-0" />
              {loginError}
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email */}
            <div>
              <label className="block text-[12px] font-semibold text-text-dim uppercase tracking-wider mb-1.5">
                Adresse email
              </label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                onBlur={() => setTouched((t) => ({ ...t, email: true }))}
                placeholder="votre@email.tn"
                autoComplete="email"
                className={`w-full px-3.5 py-2.5 bg-secondary border rounded-xl text-[13px] text-foreground placeholder:text-text-dim outline-none transition-all duration-200 focus:ring-1 focus:ring-primary/40
                  ${emailError ? "border-red-500/60 focus:border-red-500" : "border-border focus:border-primary"}`}
              />
              {emailError && (
                <p className="text-red-400 text-[11px] mt-1">{emailError}</p>
              )}
            </div>

            {/* Password */}
            <div>
              <label className="block text-[12px] font-semibold text-text-dim uppercase tracking-wider mb-1.5">
                Mot de passe
              </label>
              <div className="relative">
                <input
                  type={showPassword ? "text" : "password"}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onBlur={() => setTouched((t) => ({ ...t, password: true }))}
                  placeholder="••••••••"
                  autoComplete="current-password"
                  className={`w-full px-3.5 py-2.5 pr-10 bg-secondary border rounded-xl text-[13px] text-foreground placeholder:text-text-dim outline-none transition-all duration-200 focus:ring-1 focus:ring-primary/40
                    ${passwordError ? "border-red-500/60 focus:border-red-500" : "border-border focus:border-primary"}`}
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-text-dim hover:text-foreground transition-colors"
                >
                  {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                </button>
              </div>
              {passwordError && (
                <p className="text-red-400 text-[11px] mt-1">{passwordError}</p>
              )}
            </div>

            {/* Submit */}
            <button
              type="submit"
              disabled={isLoading}
              className="w-full flex items-center justify-center gap-2 py-2.5 rounded-xl bg-primary text-white text-[13px] font-semibold hover:bg-primary/90 disabled:opacity-60 disabled:cursor-not-allowed transition-all duration-200 shadow-lg shadow-primary/30 hover:shadow-primary/50 hover:scale-[1.01] active:scale-[0.99] mt-2"
            >
              {isLoading ? (
                <>
                  <Loader2 size={15} className="animate-spin" />
                  Connexion en cours…
                </>
              ) : (
                "Se connecter"
              )}
            </button>
          </form>

          {/* Demo accounts */}
          <div className="mt-8">
            <p className="text-[11px] text-text-dim font-semibold uppercase tracking-wider mb-3 text-center">
              Comptes de démonstration
            </p>
            <div className="space-y-2">
              {DEMO_ACCOUNTS.map((acc) => (
                <button
                  key={acc.email}
                  onClick={() => fillDemo(acc)}
                  disabled={isLoading}
                  className="w-full flex items-center justify-between px-3.5 py-2.5 rounded-xl border border-border/60 bg-secondary/50 hover:border-primary/40 hover:bg-primary/5 transition-all duration-150 text-left group disabled:opacity-40"
                >
                  <div>
                    <p className="text-[12px] font-medium text-foreground group-hover:text-primary transition-colors">
                      {acc.role}
                    </p>
                    <p className="text-[10px] text-text-dim truncate">{acc.email}</p>
                  </div>
                  <span className="text-[10px] text-text-dim font-mono bg-surface-hover px-2 py-0.5 rounded">
                    {acc.password}
                  </span>
                </button>
              ))}
            </div>
          </div>

          <p className="text-center text-[11px] text-text-dim mt-8">
            Problème de connexion ?{" "}
            <a href="mailto:support@siad.tn" className="text-primary hover:underline">
              Contacter le support
            </a>
          </p>
        </div>
      </div>
    </div>
  );
}
