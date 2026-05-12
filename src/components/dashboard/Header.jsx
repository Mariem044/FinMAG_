import { Sun, Moon, Menu, Sparkles, LogOut, ChevronDown } from "lucide-react";
import { Link, useNavigate } from "@tanstack/react-router";
import { useTheme } from "@/store/useTheme";
import { useSidebar } from "@/store/useSidebar";
import { useParametres } from "@/store/useParametres";
import { useAuth } from "@/store/useAuth";
import { SearchBar } from "@/components/dashboard/SearchBar";
import { NotificationBell } from "@/components/dashboard/NotificationBell";
import { useState, useRef, useEffect } from "react";

export function Header({ pathname }) {
  const { isDark, toggle: toggleTheme } = useTheme();
  const { toggle: toggleSidebar } = useSidebar();
  const { t } = useParametres();
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef(null);

  const pageNameKeys = {
    "/": "nav.dashboard",
    "/ventes": "nav.ventes",
    "/tresorerie": "nav.tresorerie",
    "/produits": "nav.produits",
    "/acteurs": "nav.acteurs",
    "/fiscalite": "nav.fiscalite",
    "/caisse": "nav.caisse",
    "/banque": "nav.banque",
    "/parametres": "nav.parametres",
    "/aide": "nav.aide",
    "/profil": "nav.profil",
    "/assistant": "nav.assistant",
  };

  const titleKey = pageNameKeys[pathname];
  const title = titleKey ? t(titleKey) : "SIAD";

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

  const roleColors = {
    Administrateur: "bg-red-500",
    Manager: "bg-blue-500",
    Analyste: "bg-violet-500",
    Consultant: "bg-orange-500",
    Auditeur: "bg-teal-500",
  };

  const iconBtn =
    "w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-foreground hover:bg-surface-hover hover:scale-110 transition-all duration-200";

  return (
    <header className="fixed top-0 left-0 right-0 lg:left-[264px] h-14 bg-sidebar-bg/95 backdrop-blur border-b border-border/90 shadow-[0_1px_0_0_rgba(59,130,246,0.18)] flex items-center justify-between px-4 z-30 gap-3">
      <div className="flex items-center gap-3 min-w-0 flex-shrink-0">
        <button onClick={toggleSidebar} className={`${iconBtn} lg:hidden`} title="Menu">
          <Menu size={18} />
        </button>
        <h2 className="text-[14px] font-semibold text-foreground truncate hidden sm:block">
          {title}
        </h2>
      </div>

      <SearchBar />

      <div className="flex items-center gap-1.5 flex-shrink-0">
        <Link
          to="/assistant"
          className="hidden sm:inline-flex items-center gap-1.5 rounded-lg
            bg-primary
            px-3 py-1.5 text-[11px] font-semibold text-white
            shadow-md shadow-primary/30
            hover:bg-primary/90 hover:shadow-lg hover:shadow-primary/40 hover:scale-[1.03]
            transition-all duration-200"
          title={t("header.aiAssistant")}
        >
          <Sparkles size={13} className="text-white/90" />
          <span>{t("header.aiAssistant")}</span>
        </Link>

        <button
          onClick={toggleTheme}
          title={isDark ? "Mode clair" : "Mode sombre"}
          className={iconBtn}
        >
          {isDark ? <Sun size={16} /> : <Moon size={16} />}
        </button>

        <NotificationBell />

        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-1.5 rounded-lg hover:bg-surface-hover transition-all duration-200 pl-1 pr-1.5 py-1"
            title={user ? `${user.prenom} ${user.nom}` : "Profil"}
          >
            <div className="w-7 h-7 rounded-lg bg-primary flex items-center justify-center text-white text-[11px] font-bold shadow-md shadow-primary/30">
              {user?.initiales ?? "-"}
            </div>
            <ChevronDown
              size={12}
              className={`text-text-dim transition-transform duration-200 hidden sm:block ${dropdownOpen ? "rotate-180" : ""}`}
            />
          </button>

          {dropdownOpen && (
            <div className="absolute right-0 top-full mt-2 w-56 bg-popover border border-border/70 rounded-xl shadow-2xl shadow-black/40 z-50 overflow-hidden">
              <div className="px-4 py-3 border-b border-border/60">
                <p className="text-[13px] font-semibold text-foreground">
                  {user?.prenom} {user?.nom}
                </p>
                <p className="text-[11px] text-text-dim truncate mt-0.5">{user?.email}</p>
                <div className="flex items-center gap-1.5 mt-2">
                  <span
                    className={`w-2 h-2 rounded-full ${roleColors[user?.role] ?? "bg-primary"}`}
                  />
                  <span className="text-[11px] text-text-dim">{user?.role}</span>
                </div>
              </div>

              <div className="p-1.5">
                <Link
                  to="/profil"
                  onClick={() => setDropdownOpen(false)}
                  className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] text-foreground hover:bg-surface-hover transition-colors"
                >
                  <div className="w-6 h-6 rounded-md bg-primary/10 flex items-center justify-center">
                    <span className="text-[10px] font-bold text-primary">
                      {user?.initiales ?? "-"}
                    </span>
                  </div>
                  Mon profil
                </Link>
                <Link
                  to="/parametres"
                  onClick={() => setDropdownOpen(false)}
                  className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] text-foreground hover:bg-surface-hover transition-colors"
                >
                  <div className="w-6 h-6 rounded-md bg-surface-hover flex items-center justify-center">
                    <Sun size={12} className="text-text-dim" />
                  </div>
                  Paramètres
                </Link>
              </div>

              <div className="p-1.5 border-t border-border/60">
                <button
                  onClick={handleLogout}
                  className="w-full flex items-center gap-2.5 px-3 py-2 rounded-lg text-[13px] text-red-400 hover:bg-red-500/10 transition-colors"
                >
                  <div className="w-6 h-6 rounded-md bg-red-500/10 flex items-center justify-center">
                    <LogOut size={12} className="text-red-400" />
                  </div>
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
