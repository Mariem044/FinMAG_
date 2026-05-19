import { memo } from "react";
import { Link, useLocation } from "@tanstack/react-router";
import { useSidebar } from "@/store/useSidebar";
import { useAuth } from "@/store/useAuth";
import {
  X,
  LayoutDashboard,
  Landmark,
  BookOpen,
  Users,
  Brain,
  Settings,
  Sparkles,
} from "lucide-react";

const navItems = [
  { to: "/", label: "CA & Produits", icon: LayoutDashboard },
  { to: "/finance", label: "Finance & Caisse", icon: Landmark },
  { to: "/comptabilite", label: "Comptabilité", icon: BookOpen },
  { to: "/acteurs", label: "Acteurs", icon: Users },
  { to: "/predictions", label: "Prédictions ML", icon: Brain },
];

const bottomItems = [
  { to: "/parametres", label: "Paramètres", icon: Settings },
];

export const Sidebar = memo(function Sidebar() {
  const location = useLocation();
  const path = location.pathname;
  const { open, setOpen } = useSidebar();
  const { user, logout } = useAuth();

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 z-40 lg:hidden sidebar-backdrop"
          onClick={() => setOpen(false)}
        />
      )}
      <aside
        className={`
          fixed left-0 top-0 bottom-0 w-[264px] bg-gradient-to-b from-sidebar-bg via-sidebar-bg/98 to-sidebar-bg/95 border-r border-border/80
          flex flex-col z-50 transition-all duration-500 ease-in-out
          shadow-xl shadow-black/40 lg:shadow-lg lg:shadow-black/20
          lg:translate-x-0
          ${open ? "translate-x-0" : "-translate-x-full"}
          backdrop-blur-sm
        `}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-5 border-b border-border">
          <div>
            <h1 className="text-[22px] leading-none font-extrabold text-foreground tracking-tight">
              FinMAG
            </h1>
            <p className="text-[10px] text-text-dim font-semibold tracking-[0.18em] uppercase mt-1">
              MAG Distribution Analytics
            </p>
          </div>
          <button
            onClick={() => setOpen(false)}
            className="lg:hidden w-7 h-7 flex items-center justify-center rounded-md text-text-muted hover:text-foreground hover:bg-surface-hover transition-all duration-300"
          >
            <X size={16} />
          </button>
        </div>

        {/* Navigation principale */}
        <nav className="flex-1 px-4 py-4 space-y-1 overflow-y-auto">
          <p className="text-[10px] font-semibold text-text-dim uppercase tracking-widest px-3 mb-2">
            Navigation
          </p>
          {navItems.map((item) => {
            const active = item.to === "/" ? path === "/" : path.startsWith(item.to);
            return (
              <Link
                key={item.to}
                to={item.to}
                onClick={() => setOpen(false)}
                className={`
                  flex items-center gap-3.5 px-3.5 py-2.5 rounded-xl text-[12px] font-medium
                  transition-all duration-150 group relative
                  ${
                    active
                      ? "bg-primary/10 text-primary border border-primary/20 shadow-[inset_3px_0_0_0_rgba(59,130,246,0.9)]"
                      : "text-text-muted hover:bg-surface-hover hover:text-foreground border border-transparent"
                  }
                `}
              >
                <item.icon
                  size={15}
                  className={`flex-shrink-0 transition-colors ${active ? "text-primary" : "text-text-dim group-hover:text-foreground"}`}
                />
                <span className="leading-tight">{item.label}</span>
                {active && (
                  <span className="ml-auto w-1.5 h-1.5 rounded-full bg-primary shadow-[0_0_8px_rgba(59,130,246,0.7)]" />
                )}
              </Link>
            );
          })}
        </nav>

        {/* Bas : Paramètres + Déconnexion */}
        <div className="border-t border-border px-3 py-3 space-y-0.5">
          {bottomItems.map((item) => {
            const active = path === item.to;
            return (
              <Link
                key={item.to}
                to={item.to}
                onClick={() => setOpen(false)}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] w-full transition-colors border
                  ${
                    active
                      ? "bg-primary/10 text-primary border-primary/20"
                      : "text-text-muted hover:bg-surface-hover hover:text-foreground border-transparent"
                  }`}
              >
                <item.icon size={16} className={active ? "text-primary flex-shrink-0" : "text-text-dim flex-shrink-0"} />
                {item.label}
              </Link>
            );
          })}

          {/* Déconnexion */}
          <button
            onClick={logout}
            className="flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] w-full text-text-muted hover:text-red-400 hover:bg-red-500/10 border border-transparent transition-colors"
          >
            <Sparkles size={16} className="text-text-dim flex-shrink-0" />
            Déconnexion
          </button>

          <p className="text-[10px] text-[#444] px-3 pt-1">FinMAG v1.0 — PFE 2026</p>
        </div>
      </aside>
    </>
  );
});
