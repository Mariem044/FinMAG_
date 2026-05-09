import { Link, useLocation, useNavigate } from "@tanstack/react-router";
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
  UserCircle,
  Sparkles,
  LogOut,
  ChevronRight,
} from "lucide-react";

const roleColors = {
  Administrateur: "bg-red-500/20 text-red-400 border-red-500/30",
  Manager:        "bg-blue-500/20 text-blue-400 border-blue-500/30",
  Analyste:       "bg-violet-500/20 text-violet-400 border-violet-500/30",
  Consultant:     "bg-orange-500/20 text-orange-400 border-orange-500/30",
  Auditeur:       "bg-teal-500/20 text-teal-400 border-teal-500/30",
};

const avatarColors = {
  Administrateur: "from-red-500/80 to-red-600/60",
  Manager:        "from-blue-500/80 to-blue-600/60",
  Analyste:       "from-violet-500/80 to-violet-600/60",
  Consultant:     "from-orange-500/80 to-orange-600/60",
  Auditeur:       "from-teal-500/80 to-teal-600/60",
};

export function Sidebar() {
  const location = useLocation();
  const path = location.pathname;
  const { open, setOpen } = useSidebar();
  const { t } = useParametres();
  const { user, logout, canAccessRoute } = useAuth();
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate({ to: "/login" });
  };

  const allNavItems = [
    { to: "/",           label: t("nav.dashboard"), icon: LayoutDashboard },
    { to: "/ventes",     label: t("nav.ventes"),    icon: TrendingUp },
    { to: "/tresorerie", label: t("nav.tresorerie"), icon: Wallet },
    { to: "/produits",   label: t("nav.produits"),  icon: Boxes },
    { to: "/acteurs",    label: t("nav.acteurs"),   icon: Users },
    { to: "/fiscalite",  label: t("nav.fiscalite"), icon: Receipt },
    { to: "/caisse",     label: t("nav.caisse"),    icon: Banknote },
    { to: "/banque",     label: t("nav.banque"),    icon: Landmark },
  ];

  // Filter nav items based on user's role permissions
  const navItems = allNavItems.filter((item) => canAccessRoute(item.to));

  const bottomItems = [
    { to: "/assistant", label: t("nav.assistant"), icon: Sparkles },
    { to: "/profil",    label: t("nav.profil"),    icon: UserCircle },
    { to: "/parametres",label: t("nav.parametres"),icon: Settings },
    { to: "/aide",      label: t("nav.aide"),      icon: HelpCircle },
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
        {/* Logo */}
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

        {/* Nav */}
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

        {/* Bottom section */}
        <div className="border-t border-border px-3 py-3 space-y-0.5">
          {bottomItems.map((item) => {
            const active = path === item.to;
            return (
              <Link
                key={item.to}
                to={item.to}
                onClick={() => setOpen(false)}
                className={`flex items-center gap-3 px-3 py-2.5 rounded-lg text-[13px] w-full transition-colors border
                  ${active
                    ? "bg-primary/10 text-primary border-primary/20"
                    : "text-text-muted hover:bg-surface-hover hover:text-foreground border-transparent"
                  }`}
              >
                <item.icon size={16} className={active ? "text-primary flex-shrink-0" : "text-text-dim flex-shrink-0"} />
                {item.label}
              </Link>
            );
          })}

          {/* Logged-in user card */}
          {user && (
            <div className="mt-2 pt-2 border-t border-border/60">
              <div className="flex items-center gap-3 px-3 py-2.5 rounded-xl bg-surface-hover/50 border border-border/40">
                {/* Avatar */}
                <div className={`w-8 h-8 rounded-lg bg-gradient-to-br ${avatarColors[user.role] ?? "from-primary/80 to-primary/60"} flex items-center justify-center flex-shrink-0 shadow-sm`}>
                  {user.avatar ? (
                    <img src={user.avatar} alt={user.initiales} className="w-full h-full object-cover rounded-lg" />
                  ) : (
                    <span className="text-[11px] font-bold text-white">{user.initiales}</span>
                  )}
                </div>

                {/* Name + role */}
                <div className="flex-1 min-w-0">
                  <p className="text-[12px] font-semibold text-foreground truncate">
                    {user.prenom} {user.nom}
                  </p>
                  <span className={`inline-flex items-center text-[9px] font-bold px-1.5 py-0.5 rounded-full border ${roleColors[user.role] ?? "bg-primary/20 text-primary border-primary/30"}`}>
                    {user.role}
                  </span>
                </div>

                {/* Logout button */}
                <button
                  onClick={handleLogout}
                  title="Déconnexion"
                  className="w-7 h-7 flex items-center justify-center rounded-lg text-text-dim hover:text-red-400 hover:bg-red-500/10 transition-all duration-200 flex-shrink-0"
                >
                  <LogOut size={13} />
                </button>
              </div>
            </div>
          )}

          <p className="text-[10px] text-[#444] px-3 pt-1">{t("common.version")}</p>
        </div>
      </aside>
    </>
  );
}
