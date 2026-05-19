import { Menu, LogOut, ChevronDown, Sun } from "lucide-react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useSidebar } from "@/store/useSidebar";
import { useAuth } from "@/store/useAuth";
import { useState, useRef, useEffect } from "react";

const pageNames = {
  "/": "CA & Produits",
  "/finance": "Finance & Caisse",
  "/comptabilite": "Comptabilité",
  "/acteurs": "Acteurs",
  "/predictions": "Prédictions ML",
  "/parametres": "Paramètres",
};

export function Header({ pathname }) {
  const { toggle: toggleSidebar } = useSidebar();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);

  const title = pageNames[pathname] ?? "FinMAG";

  useEffect(() => {
    function handler(e) {
      if (!dropdownRef.current?.contains(e.target)) setDropdownOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const handleLogout = () => {
    logout();
    navigate({ to: "/login" });
  };

  return (
    <header className="fixed top-0 left-0 right-0 lg:left-[264px] h-14 bg-sidebar-bg/95 backdrop-blur border-b border-border flex items-center justify-between px-4 z-30 gap-3">
      {/* Titre */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={toggleSidebar}
          className="lg:hidden w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:bg-surface-hover"
        >
          <Menu size={18} />
        </button>
        <h2 className="text-[14px] font-semibold text-foreground hidden sm:block">{title}</h2>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        {/* Dropdown utilisateur */}
        <div className="relative" ref={dropdownRef}>
          <button
            type="button"
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-1.5 px-2 py-1 rounded-lg hover:bg-surface-hover transition-colors"
          >
            <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center text-white text-[11px] font-bold">
              {user?.initiales ?? "MA"}
            </div>
            <ChevronDown size={12} className="text-text-dim hidden sm:block" />
          </button>

          {dropdownOpen && (
            <div className="absolute right-0 top-full mt-2 w-48 bg-card border border-border rounded-xl shadow-xl z-50 overflow-hidden">
              <div className="px-4 py-3 border-b border-border">
                <p className="text-[13px] font-semibold text-foreground">{user?.prenom} {user?.nom}</p>
                <p className="text-[11px] text-text-dim">{user?.poste}</p>
              </div>
              <div className="p-1.5">
                <Link
                  to="/parametres"
                  onClick={() => setDropdownOpen(false)}
                  className="flex items-center gap-2 px-3 py-2 rounded-lg text-[13px] text-foreground hover:bg-surface-hover"
                >
                  <Sun size={14} className="text-text-dim" />
                  Paramètres
                </Link>
                <button
                  type="button"
                  onClick={handleLogout}
                  className="w-full flex items-center gap-2 px-3 py-2 rounded-lg text-[13px] text-red-400 hover:bg-red-500/10"
                >
                  <LogOut size={14} />
                  Déconnexion
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
