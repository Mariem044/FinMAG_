// FIXED: Added disabled prop to skip ETL status display/polling on irrelevant routes.
import { Link } from "@tanstack/react-router";
import { AlertTriangle, Database, Loader2 } from "lucide-react";
import { useEffect, useCallback, useState } from "react";
import { api } from "@/lib/api";

const POLL_RUNNING_MS  = 3_000;   // fast poll while ETL is active
const POLL_IDLE_MS     = 30_000;  // slow poll when nothing is running

export function DataSourceStatus({ disabled = false }) {
  const defaultData = { running: false, lastRun: null, counts: {} };
  const [data,      setData]      = useState(defaultData);
  const [error,     setError]     = useState(null);
  const [loading,   setLoading]   = useState(true);
  const [hasRealData, setHasRealData] = useState(false);

  const fetch = useCallback(() => {
    api.etl.status()
      .then((d) => {
        setData(d ?? defaultData);
        setError(null);
        setHasRealData(true);
      })
      .catch((e) => {
        setError(e);
        setHasRealData(false);
      })
      .finally(() => setLoading(false));
  }, []);  // eslint-disable-line react-hooks/exhaustive-deps

  // FIX: poll continuously instead of fetching once on mount.
  // Use a short interval while the ETL is running so the UI transitions
  // to "done" promptly; use a long interval when idle to save DB load.
  useEffect(() => {
    if (disabled) return undefined;
    fetch(); // immediate first fetch
    const interval = setInterval(fetch, data.running ? POLL_RUNNING_MS : POLL_IDLE_MS);
    return () => clearInterval(interval);
  }, [disabled, fetch, data.running]);

  if (disabled) return null;

  if (loading) {
    return (
      <div className="mb-4 flex items-center gap-2 rounded-lg border border-border/70 bg-secondary/30 px-3 py-2 text-xs text-text-dim">
        <Loader2 size={14} className="animate-spin" />
        Connexion aux donnees ETL...
      </div>
    );
  }

  if (error || !hasRealData) {
    return (
      <div className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-200">
        <span className="flex items-center gap-2">
          <AlertTriangle size={14} />
          API ETL indisponible. Les tableaux attendent les donnees reelles du DW.
        </span>
        <Link
          to="/parametres"
          className="font-semibold text-red-100 underline-offset-4 hover:underline"
        >
          Verifier
        </Link>
      </div>
    );
  }

  // Safe null-check: data or data.counts may be undefined on first render
  const counts = data?.counts || {};
  const totalRows = Object.values(counts).reduce((sum, value) => sum + Number(value || 0), 0);

  if (totalRows === 0) {
    return (
      <div className="mb-4 flex items-center justify-between gap-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
        <span className="flex items-center gap-2">
          <Database size={14} />
          API connectee, mais le DW est vide. Lancez l'ETL pour extraire MAG_2020 et GRT_MAG.
        </span>
        <Link
          to="/parametres"
          className="font-semibold text-amber-50 underline-offset-4 hover:underline"
        >
          Lancer ETL
        </Link>
      </div>
    );
  }

  return (
    <div className="mb-4 flex flex-wrap items-center gap-x-4 gap-y-1 rounded-lg border border-emerald-500/20 bg-emerald-500/10 px-3 py-2 text-xs text-emerald-100">
      <span className="flex items-center gap-2 font-semibold">
        <Database size={14} />
        Donnees DW reelles connectees
      </span>
      <span>{(counts.ventes || 0).toLocaleString("fr-TN")} ventes</span>
      <span>{(counts.reglements || 0).toLocaleString("fr-TN")} reglements</span>
      <span>{(counts.ecritures || 0).toLocaleString("fr-TN")} ecritures</span>
      {data?.running && <span className="font-semibold">ETL en cours</span>}
    </div>
  );
}
