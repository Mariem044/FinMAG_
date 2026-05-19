import { createFileRoute, useNavigate } from "@tanstack/react-router";
import { useEffect } from "react";
import { BarChart2 } from "lucide-react";
import { useAuth } from "@/store/useAuth";

export const Route = createFileRoute("/login")({
  component: LoginPage,
});

function LoginPage() {
  const navigate = useNavigate();
  const { enterAsAdmin, isAuthenticated } = useAuth();

  useEffect(() => {
    if (isAuthenticated) {
      navigate({ to: "/" });
    }
  }, [isAuthenticated, navigate]);

  const handleEnter = () => {
    enterAsAdmin();
    navigate({ to: "/" });
  };

  return (
    <div className="min-h-screen bg-background flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <div className="w-10 h-10 rounded-xl bg-primary flex items-center justify-center">
            <BarChart2 size={20} className="text-white" />
          </div>
          <span className="text-2xl font-bold text-foreground">FinMAG</span>
        </div>

        {/* Card */}
        <div className="bg-card border border-border rounded-xl p-8 space-y-6">
          <div className="text-center">
            <h1 className="text-xl font-bold text-foreground">Bienvenue</h1>
            <p className="text-sm text-text-dim mt-1">
              Dashboard analytique MAG Distribution
            </p>
          </div>

          <button
            type="button"
            onClick={handleEnter}
            className="w-full py-3 rounded-lg bg-primary text-white font-semibold text-sm hover:bg-primary/90 transition-colors"
          >
            Entrer en tant qu'admin
          </button>

          <p className="text-center text-xs text-text-dim">
            MAG Distribution — Projet PFE 2026
          </p>
        </div>
      </div>
    </div>
  );
}
