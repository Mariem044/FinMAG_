import { memo } from "react";
import { Link, useLocation } from "@tanstack/react-router";
import { useSidebar } from "@/store/useSidebar";
import { useParametres } from "@/store/useParametres";
import { useAuth } from "@/store/useAuth";
import {
  X,
  LayoutDashboard,
  TrendingUp,
  Wallet,
  Boxes,
  Users,
  Receipt,
  Landmark,
  Banknote,
  Settings,
  HelpCircle,
  Sparkles,
} from "lucide-react";

export const Sidebar = memo(function Sidebar() {
  const location = useLocation();
  const path = location.pathname;
  const { open, setOpen } = useSidebar();
  const { t } = useParametres();
  const { canAccessRoute } = useAuth();

  const allNavItems = [
    { to: "/", label: t("nav.dashboard"), icon: LayoutDashboard },
    { to: "/ventes", label: t("nav.ventes"), icon: TrendingUp },
    { to: "/tresorerie", label: t("nav.tresorerie"), icon: Wallet },
    { to: "/produits", label: t("nav.produits"), icon: Boxes },
    { to: "/acteurs", label: t("nav.acteurs"), icon: Users },
    { to: "/fiscalite", label: t("nav.fiscalite"), icon: Receipt },
    { to: "/caisse", label: t("nav.caisse"), icon: Banknote },
    { to: "/banque", label: t("nav.banque"), icon: Landmark },
  ];

  const navItems = allNavItems.filter((item) => canAccessRoute(item.to));

  const bottomItems = [
    { to: "/assistant", label: t("nav.assistant"), icon: Sparkles },
    { to: "/parametres", label: t("nav.parametres"), icon: Settings },
    { to: "/aide", label: t("nav.aide"), icon: HelpCircle },
  ].filter((item) => canAccessRoute(item.to));

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

        <nav className="flex-1 px-4 py-4 space-y-1 overflow-y-auto">
          <p className="text-[10px] font-semibold text-text-dim uppercase tracking-widest px-3 mb-2">
            {t("nav.domains")}
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
                <item.icon
                  size={16}
                  className={active ? "text-primary flex-shrink-0" : "text-text-dim flex-shrink-0"}
                />
                {item.label}
              </Link>
            );
          })}

          <p className="text-[10px] text-[#444] px-3 pt-1">{t("common.version")}</p>
        </div>
      </aside>
    </>
  );
});
