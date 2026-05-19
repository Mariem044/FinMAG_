import { createFileRoute } from "@tanstack/react-router";
import { useChartHeight, ChartCard, KPICardSkeleton } from "@/components/dashboard/ChartCard";
import { KPICard } from "@/components/dashboard/KPICard";
import { CustomTooltip } from "@/components/dashboard/CustomTooltip";
import { Banknote, AlertCircle, Receipt, Activity, ShieldAlert } from "lucide-react";
import {
  BarChart, Bar, ComposedChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  ResponsiveContainer, ReferenceLine, Cell,
  ScatterChart, Scatter, ZAxis,
} from "recharts";
import { formatTND } from "@/lib/dashboardConstants";
import { useFilters } from "@/store/useFilters";
import { useMemo } from "react";
import { api } from "@/lib/api";
import { useApiResource } from "@/hooks/useApiResource";

export const Route = createFileRoute("/comptabilite")({
  component: ComptabilitePage,
});

function AnomalyDot(props) {
  const { cx, cy, payload } = props;
  if (payload?.anomalie) {
    return <circle cx={cx} cy={cy} r={6} fill="#ef4444" stroke="#ff000044" strokeWidth={3} opacity={0.9} />;
  }
  return <circle cx={cx} cy={cy} r={3} fill="#3b82f6" opacity={0.4} />;
}

function ComptabilitePage() {
  const { year, quarter } = useFilters();
  const chartH = useChartHeight();

  const summaryFn = useMemo(() => () => api.tresorerie.summary(), [year, quarter]);
  const agingFn   = useMemo(() => () => api.tresorerie.aging(),   [year, quarter]);
  const fiscKpisFn = useMemo(() => () => api.fiscalite.kpis(),   [year, quarter]);
  const tvaDataFn  = useMemo(() => () => api.fiscalite.tvaByMonth(), [year, quarter]);
  const anomalyDataFn = useMemo(() => () => api.fiscalite.anomalies(), [year, quarter]);

  // ── Trésorerie data ──
  const { data: summary, loading: summaryLoading } = useApiResource(summaryFn, {
    encaissements: 0, impayes: 0, delai_moyen: 0, taux_recouvrement: 0,
  });
  const { data: agingData, loading: agingLoading } = useApiResource(agingFn, []);

  // ── Fiscalité data ──
  const { data: fiscKpis, loading: fiscLoading } = useApiResource(fiscKpisFn, {
    nb_ecritures: 0, tva_collectee: 0, tva_deductible: 0, anomalies: 0, equilibre_pct: 0,
  });
  const { data: tvaData, loading: tvaLoading } = useApiResource(tvaDataFn, []);
  const { data: anomalyData, loading: anomaliesLoading } = useApiResource(anomalyDataFn, []);

  const kpiLoading = summaryLoading || fiscLoading;
  const chartsLoading = summaryLoading || agingLoading || tvaLoading || anomaliesLoading;

  const safeAgingData = useMemo(() =>
    (Array.isArray(agingData) ? agingData : []).filter(Boolean).map((row) => ({
      client: row.client || "Client",
      "0-30j": Number(row["0-30j"]) || 0,
      "31-60j": Number(row["31-60j"]) || 0,
      "61-90j": Number(row["61-90j"]) || 0,
      ">90j": Number(row[">90j"]) || 0,
    })), [agingData]);

  const gt90 = safeAgingData.reduce((sum, row) => sum + row[">90j"], 0);

  return (
    <div className="space-y-6">
      {/* ── 5 KPIs ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4">
        {kpiLoading ? (
          <>
            <KPICardSkeleton />
            <KPICardSkeleton />
            <KPICardSkeleton />
            <KPICardSkeleton />
            <KPICardSkeleton />
          </>
        ) : (
          <>
            <KPICard
              label="Encaissements Clients"
              value={formatTND(summary.encaissements)}
              subtitle={`Taux Recov. : ${Math.round(summary.taux_recouvrement || 0)}% | DSO : ${summary.delai_moyen}j`}
              icon={Banknote}
            />
            <KPICard
              label="Créances Impayées"
              value={formatTND(Math.round(summary.impayes))}
              subtitle={`dont ${formatTND(gt90)} de plus de 90 jours`}
              icon={AlertCircle}
            />
            <KPICard
              label="TVA collectée depuis janvier"
              value={formatTND(fiscKpis?.tva_collectee || 0)}
              subtitle={`${formatTND(fiscKpis?.tva_deductible || 0)} déductible`}
              icon={Receipt}
            />
            <KPICard
              label="Taux Équilibre D/C"
              value={`${(fiscKpis?.equilibre_pct ?? 100).toFixed(2)}%`}
              subtitle="Intégrité des écritures"
              icon={Activity}
            />
            <KPICard
              label="Score d'Anomalie"
              value={`${fiscKpis?.anomalies ?? 0} signaux`}
              subtitle={`sur ${fiscKpis?.nb_ecritures?.toLocaleString("fr-TN") ?? 0} écritures`}
              icon={ShieldAlert}
            />
          </>
        )}
      </div>

      {/* Section Trésorerie */}
      <div className="flex items-center gap-3">
        <span className="text-[11px] font-bold uppercase tracking-widest text-text-dim">Trésorerie</span>
        <div className="flex-1 h-px bg-border/30" />
      </div>
      <div className="grid grid-cols-1 gap-4">
        <ChartCard loading={chartsLoading} skeleton="bar" title="Répartition des créances par ancienneté">
          <ResponsiveContainer width="100%" height={chartH}>
            <BarChart data={safeAgingData}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="client" tick={{ fill: "#666", fontSize: 10 }} axisLine={false} />
              <YAxis tick={{ fill: "#666", fontSize: 10 }} axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11, color: "#888" }} />
              <Bar dataKey="0-30j" stackId="age" fill="#22c55e" name="0 à 30 jours" />
              <Bar dataKey="31-60j" stackId="age" fill="#f97316" name="31 à 60 jours" />
              <Bar dataKey="61-90j" stackId="age" fill="#a855f7" name="61 à 90 jours" />
              <Bar dataKey=">90j" stackId="age" fill="#ef4444" name="Plus de 90 jours" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      {/* Section Fiscalité */}
      <div className="flex items-center gap-3">
        <span className="text-[11px] font-bold uppercase tracking-widest text-text-dim">Fiscalité</span>
        <div className="flex-1 h-px bg-border/30" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard loading={chartsLoading} skeleton="bar" title="TVA collectée et TVA déductible">
          <ResponsiveContainer width="100%" height={chartH}>
            <ComposedChart data={tvaData}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="month" tick={{ fill: "#666", fontSize: 11 }} axisLine={false} />
              <YAxis yAxisId="left" tick={{ fill: "#666", fontSize: 11 }} axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#888" }} />
              <Bar yAxisId="left" dataKey="soldeNet" fill="#22c55e" opacity={0.4}
                radius={[4, 4, 0, 0]} name="Solde net TVA" />
              <Line yAxisId="left" type="monotone" dataKey="collectee"
                stroke="#3b82f6" strokeWidth={2} dot={false} name="TVA collectée" />
              <Line yAxisId="left" type="monotone" dataKey="deductible"
                stroke="#ef4444" strokeWidth={2} dot={false} name="TVA déductible" />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard loading={chartsLoading} skeleton="scatter" title="Détection anomalies comptables">
          <ResponsiveContainer width="100%" height={chartH}>
            <ScatterChart margin={{ top: 10, right: 10, bottom: 20, left: 10 }}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="date" name="Date" tick={{ fill: "#666", fontSize: 9 }}
                axisLine={false} angle={-30} textAnchor="end" height={40} />
              <YAxis dataKey="score" name="Score anomalie" tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false} domain={[0, 1]}
                label={{ value: "Score (0-1)", angle: -90, position: "insideLeft", fill: "#555", fontSize: 10 }} />
              <ZAxis dataKey="montant" range={[30, 300]} name="Montant" />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={0.8} stroke="#ef4444" strokeDasharray="4 4"
                label={{ value: "Seuil 0.8", fill: "#ef4444", fontSize: 10, position: "right" }} />
              <Scatter data={anomalyData} shape={AnomalyDot} name="Écriture" />
            </ScatterChart>
          </ResponsiveContainer>
          <p className="text-[10px] text-text-dim mt-1 text-right">
            <span className="inline-flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-red-500 inline-block" />
              {(Array.isArray(anomalyData) ? anomalyData : []).filter((d) => d?.anomalie).length} anomalies (score &gt; 0.8)
            </span>
          </p>
        </ChartCard>
      </div>
    </div>
  );
}
