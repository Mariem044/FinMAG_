import { useState, useRef, useEffect, useMemo } from "react";
import { Bell, AlertTriangle, Clock, X, ChevronRight, CheckCheck, Package, Banknote } from "lucide-react";
import { articles, impayes } from "@/data/mockData";

function useNotifications() {
  return useMemo(() => {
    // Critical stock alerts: articles where qteVendue < 500 (simulate low stock)
    const stockAlerts = articles
      .filter((a) => a.qteVendue < 500)
      .slice(0, 6)
      .map((a) => ({
        id: `stock-${a.code}`,
        type: "stock",
        severity: a.qteVendue < 200 ? "critical" : "warning",
        title: a.designation,
        message: `Stock critique — ${a.qteVendue} unités restantes`,
        meta: a.famille,
        time: "Il y a " + (Math.floor(Math.random() * 3) + 1) + "h",
      }));

    // Overdue payment alerts: impayes where anciennete > 60
    const paymentAlerts = impayes
      .filter((i) => i.anciennete > 60)
      .slice(0, 6)
      .map((i) => ({
        id: `pay-${i.client}-${i.anciennete}`,
        type: "payment",
        severity: i.anciennete > 90 ? "critical" : "warning",
        title: i.client,
        message: `Impayé ${i.anciennete}j — ${new Intl.NumberFormat("fr-TN").format(i.montantImpaye)} DT`,
        meta: i.region,
        time: `Échéance ${i.dateEcheance}`,
      }));

    const all = [...stockAlerts, ...paymentAlerts]
      .sort((a, b) => (a.severity === "critical" ? -1 : 1));

    return {
      all,
      critical: all.filter((n) => n.severity === "critical").length,
    };
  }, []);
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [dismissed, setDismissed] = useState(new Set());
  const [activeTab, setActiveTab] = useState("all");
  const ref = useRef(null);
  const { all, critical } = useNotifications();

  const visible = all.filter((n) => !dismissed.has(n.id));
  const stockVisible = visible.filter((n) => n.type === "stock");
  const paymentVisible = visible.filter((n) => n.type === "payment");
  const shown = activeTab === "stock" ? stockVisible : activeTab === "payment" ? paymentVisible : visible;

  useEffect(() => {
    function handler(e) {
      if (!ref.current?.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  const dismiss = (id, e) => {
    e.stopPropagation();
    setDismissed((prev) => new Set([...prev, id]));
  };

  const dismissAll = () => {
    setDismissed(new Set(all.map((n) => n.id)));
  };

  const badgeCount = visible.filter((n) => n.severity === "critical").length;

  return (
    <div className="relative" ref={ref}>
      {/* Bell button */}
      <button
        onClick={() => setOpen(!open)}
        className="w-8 h-8 flex items-center justify-center rounded-lg text-text-muted hover:text-foreground hover:bg-surface-hover hover:scale-110 transition-all duration-200 relative"
        title="Notifications"
      >
        <Bell size={16} />
        {badgeCount > 0 && (
          <span className="absolute -top-0.5 -right-0.5 w-4 h-4 rounded-full bg-red-500 text-white text-[9px] font-bold flex items-center justify-center shadow-lg shadow-red-500/40 animate-pulse">
            {badgeCount > 9 ? "9+" : badgeCount}
          </span>
        )}
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 top-full mt-2 w-[360px] bg-popover border border-border/70 rounded-2xl shadow-2xl shadow-black/40 z-50 overflow-hidden">
          {/* Header */}
          <div className="px-4 pt-4 pb-3 border-b border-border/60 flex items-center justify-between">
            <div>
              <h3 className="text-[14px] font-bold text-foreground">Notifications</h3>
              <p className="text-[11px] text-text-dim mt-0.5">
                {visible.length} alerte{visible.length !== 1 ? "s" : ""} active{visible.length !== 1 ? "s" : ""}
              </p>
            </div>
            {visible.length > 0 && (
              <button
                onClick={dismissAll}
                className="flex items-center gap-1.5 text-[11px] text-primary hover:text-primary/80 font-medium transition-colors"
              >
                <CheckCheck size={13} />
                Tout effacer
              </button>
            )}
          </div>

          {/* Tabs */}
          <div className="flex border-b border-border/60 px-2 pt-2">
            {[
              { key: "all", label: "Tout", count: visible.length },
              { key: "stock", label: "Stocks", count: stockVisible.length },
              { key: "payment", label: "Impayés", count: paymentVisible.length },
            ].map((tab) => (
              <button
                key={tab.key}
                onClick={() => setActiveTab(tab.key)}
                className={`flex items-center gap-1.5 px-3 py-1.5 text-[11px] font-semibold rounded-t-lg transition-all mr-1 border-b-2 ${
                  activeTab === tab.key
                    ? "border-primary text-primary"
                    : "border-transparent text-text-dim hover:text-foreground"
                }`}
              >
                {tab.label}
                {tab.count > 0 && (
                  <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full ${
                    activeTab === tab.key ? "bg-primary/20 text-primary" : "bg-border text-text-dim"
                  }`}>
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* List */}
          <div className="max-h-[340px] overflow-y-auto">
            {shown.length === 0 ? (
              <div className="py-10 text-center">
                <CheckCheck size={28} className="text-green-400 mx-auto mb-2" />
                <p className="text-[13px] font-medium text-foreground">Tout est en ordre !</p>
                <p className="text-[11px] text-text-dim mt-1">Aucune alerte active dans cette catégorie</p>
              </div>
            ) : (
              <div className="p-2 space-y-1">
                {shown.map((n) => (
                  <div
                    key={n.id}
                    className={`group flex items-start gap-3 p-3 rounded-xl transition-all duration-150 hover:bg-surface-hover/60 border ${
                      n.severity === "critical"
                        ? "border-red-500/20 bg-red-500/5"
                        : "border-orange-500/15 bg-orange-500/5"
                    }`}
                  >
                    {/* Icon */}
                    <div className={`w-8 h-8 rounded-lg flex items-center justify-center flex-shrink-0 ${
                      n.severity === "critical"
                        ? n.type === "stock"
                          ? "bg-red-500/20"
                          : "bg-red-500/20"
                        : "bg-orange-500/20"
                    }`}>
                      {n.type === "stock"
                        ? <Package size={14} className={n.severity === "critical" ? "text-red-400" : "text-orange-400"} />
                        : <Banknote size={14} className={n.severity === "critical" ? "text-red-400" : "text-orange-400"} />
                      }
                    </div>

                    {/* Content */}
                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-[12px] font-semibold text-foreground truncate">{n.title}</p>
                        <button
                          onClick={(e) => dismiss(n.id, e)}
                          className="opacity-0 group-hover:opacity-100 transition-opacity text-text-dim hover:text-foreground flex-shrink-0"
                        >
                          <X size={12} />
                        </button>
                      </div>
                      <p className="text-[11px] text-text-dim mt-0.5 leading-relaxed">{n.message}</p>
                      <div className="flex items-center gap-2 mt-1.5">
                        <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider ${
                          n.severity === "critical"
                            ? "bg-red-500/20 text-red-400"
                            : "bg-orange-500/20 text-orange-400"
                        }`}>
                          {n.severity === "critical" ? "Critique" : "Attention"}
                        </span>
                        <span className="text-[10px] text-text-dim">{n.meta}</span>
                        <span className="text-[10px] text-text-dim ml-auto flex items-center gap-1">
                          <Clock size={9} />
                          {n.time}
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Footer */}
          <div className="px-4 py-3 border-t border-border/60 flex items-center justify-between">
            <span className="text-[10px] text-text-dim">
              Alertes calculées depuis les données locales
            </span>
            <a
              href="/produits"
              onClick={() => setOpen(false)}
              className="flex items-center gap-1 text-[11px] text-primary hover:text-primary/80 font-medium transition-colors"
            >
              Voir stocks
              <ChevronRight size={12} />
            </a>
          </div>
        </div>
      )}
    </div>
  );
}
