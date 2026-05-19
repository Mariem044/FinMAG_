import { createFileRoute } from "@tanstack/react-router";
import { useState, useMemo } from "react";
import { api } from "@/lib/api";
import { useApiResource } from "@/hooks/useApiResource";
import { useTheme } from "@/store/useTheme";
import { Database, Play, RefreshCw, CheckCircle, XCircle, Clock, Sun, Moon } from "lucide-react";


export const Route = createFileRoute("/parametres")({
  component: ParametresPage,
});

// Clés retournées par /api/etl/status → counts
const ETL_COUNT_KEYS = [
  { key: "clients",    label: "Clients" },
  { key: "articles",   label: "Articles" },
  { key: "ventes",     label: "Lignes ventes" },
  { key: "reglements", label: "Règlements" },
  { key: "ecritures",  label: "Écritures" },
];

function StatusBadge({ status }) {
  if (!status) return null;
  const isOk = status === "success" || status === "ok" || status === "completed";
  const isErr = status === "error" || status === "failed";
  const label = isOk ? "Réussi" : isErr ? "Erreur" : "En cours";
  return (
    <span
      className={`inline-flex items-center gap-1 text-[11px] font-semibold px-2 py-0.5 rounded-full ${
        isOk ? "bg-green-500/15 text-green-400"
             : isErr ? "bg-red-500/15 text-red-400"
             : "bg-orange-500/15 text-orange-400"
      }`}
    >
      {isOk ? <CheckCircle size={11} /> : isErr ? <XCircle size={11} /> : <Clock size={11} />}
      {label}
    </span>
  );
}

function ParametresPage() {
  const { isDark, toggle } = useTheme();
  const [refreshKey, setRefreshKey] = useState(0);
  const [etlAction, setEtlAction] = useState("");

  // useMemo pour que useApiResource re-fetch quand refreshKey change
  const etlStatusFn = useMemo(() => () => api.etl.status(), [refreshKey]);
  const { data: etlStatus, loading: etlLoading } = useApiResource(
    etlStatusFn,
    { running: false, lastRun: null, counts: {}, lastError: null }
  );

  async function handleRunEtl() {
    setEtlAction("Démarrage en cours...");
    try {
      const result = await api.etl.run();
      setEtlAction(
        result.started
          ? "✓ ETL démarré avec succès"
          : "⚠ ETL déjà en cours d'exécution"
      );
      // Rafraîchir le statut après 2s
      setTimeout(() => setRefreshKey((v) => v + 1), 2000);
    } catch {
      setEtlAction("✗ Erreur lors du démarrage de l'ETL");
    }
  }

  const lastRun = etlStatus?.lastRun;
  const counts  = etlStatus?.counts || {};

  return (
    <div className="space-y-6 max-w-2xl">
      <h1 className="text-3xl font-bold text-foreground">Paramètres</h1>

      {/* ── Apparence ── */}
      <div className="bg-card border border-border rounded-xl p-6">
        <h2 className="text-lg font-semibold text-foreground mb-4">Apparence</h2>
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm font-medium text-foreground">Thème</p>
            <p className="text-xs text-text-dim mt-0.5">Choisir entre le mode clair et sombre</p>
          </div>
          <button
            onClick={toggle}
            className="flex items-center gap-2 px-4 py-2 border border-border rounded-lg text-foreground hover:bg-secondary transition-colors text-sm"
          >
            {isDark ? <Sun size={15} /> : <Moon size={15} />}
            {isDark ? "Mode clair" : "Mode sombre"}
          </button>
        </div>
      </div>

      {/* ── Pipeline ETL ── */}
      <div className="bg-card border border-border rounded-xl p-6 space-y-5">
        <div className="flex items-center gap-2">
          <Database size={18} className="text-primary" />
          <h2 className="text-lg font-semibold text-foreground">Pipeline ETL</h2>
          {etlStatus?.running && (
            <span className="text-[11px] font-semibold px-2 py-0.5 rounded-full bg-blue-500/15 text-blue-400 animate-pulse">
              En cours…
            </span>
          )}
        </div>

        {/* Dernière exécution */}
        <div className="rounded-lg border border-border bg-secondary/30 p-4 space-y-3">
          <div className="flex items-center justify-between text-sm">
            <span className="text-text-dim font-medium">Dernière exécution</span>
            {etlLoading ? (
              <span className="text-text-dim text-xs">Chargement…</span>
            ) : lastRun ? (
              <div className="flex items-center gap-2">
                <StatusBadge status={lastRun.status} />
                <span className="text-foreground text-xs font-mono">
                  {/* Affiche la date et durée si disponibles */}
                  {lastRun.date
                    ? new Date(lastRun.date).toLocaleString("fr-TN")
                    : "—"}
                  {lastRun.durationSeconds
                    ? ` — ${lastRun.durationSeconds}s`
                    : ""}
                </span>
              </div>
            ) : (
              <span className="text-text-dim text-xs italic">Aucune exécution enregistrée</span>
            )}
          </div>

          {/* Erreur éventuelle */}
          {(etlStatus?.lastError || lastRun?.error) && (
            <div className="text-xs text-red-400 bg-red-500/10 rounded-lg px-3 py-2 font-mono break-all">
              {etlStatus?.lastError || lastRun?.error}
            </div>
          )}

          {/* Compteurs */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 pt-1">
            {ETL_COUNT_KEYS.map(({ key, label }) => (
              <div key={key} className="text-center bg-background rounded-lg p-2 border border-border/50">
                <p className="text-text-dim uppercase text-[9px] tracking-wider font-semibold mb-1">
                  {label}
                </p>
                <p className="text-foreground font-bold text-sm">
                  {etlLoading
                    ? "…"
                    : (counts[key] ?? 0).toLocaleString("fr-TN")}
                </p>
              </div>
            ))}
          </div>

          {/* Actions */}
          <div className="flex items-center justify-between gap-3 pt-1">
            <span className={`text-xs font-medium ${
              etlAction.startsWith("✓") ? "text-green-400"
              : etlAction.startsWith("✗") ? "text-red-400"
              : "text-text-dim"
            }`}>
              {etlAction}
            </span>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setRefreshKey((v) => v + 1)}
                className="flex items-center gap-1.5 px-3 py-2 border border-border rounded-lg text-foreground hover:bg-secondary transition-colors text-sm"
              >
                <RefreshCw size={13} />
                Rafraîchir
              </button>
              <button
                type="button"
                onClick={handleRunEtl}
                disabled={etlStatus?.running}
                className="flex items-center gap-1.5 px-3 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 disabled:opacity-50 transition-colors text-sm font-semibold"
              >
                <Play size={13} />
                {etlStatus?.running ? "ETL en cours…" : "Lancer l'ETL"}
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
