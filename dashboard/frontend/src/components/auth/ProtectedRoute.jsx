import { useEffect } from "react";
import { useNavigate, useLocation } from "@tanstack/react-router";
import { useAuth } from "@/store/useAuth";
import { ShieldOff } from "lucide-react";

export function ProtectedRoute({ children }) {
  const { isAuthenticated, canAccessRoute } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (!isAuthenticated) {
      navigate({ to: "/login" });
    }
  }, [isAuthenticated, navigate]);

  if (!isAuthenticated) return null;

  const hasAccess = canAccessRoute(location.pathname);

  if (!hasAccess) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4">
        <div className="w-16 h-16 rounded-2xl bg-red-500/10 border border-red-500/20 flex items-center justify-center">
          <ShieldOff size={28} className="text-red-400" />
        </div>
        <div className="text-center">
          <h2 className="text-lg font-bold text-foreground">Accès refusé</h2>
          <p className="text-text-dim text-[13px] mt-1 max-w-xs">
            Vous n'avez pas les permissions nécessaires pour accéder à cette page.
          </p>
        </div>
        <button
          onClick={() => navigate({ to: "/" })}
          className="px-4 py-2 rounded-lg bg-primary text-white text-[13px] font-medium hover:bg-primary/90 transition-colors"
        >
          Retour au tableau de bord
        </button>
      </div>
    );
  }

  return children;
}
