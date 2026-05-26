import { createFileRoute } from "@tanstack/react-router";
import {
  useChartHeight,
  ChartCard,
  KPICardSkeleton,
} from "@/components/dashboard/ChartCard";
import { KPICard } from "@/components/dashboard/KPICard";
import { CustomTooltip } from "@/components/dashboard/CustomTooltip";
import {
  Banknote,
  AlertCircle,
  Receipt,
  Activity,
  ShieldAlert,
} from "lucide-react";
import {
  BarChart,
  Bar,
  ComposedChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  Cell,
  ScatterChart,
  Scatter,
  ZAxis,
} from "recharts";
import {
  BUSINESS_THRESHOLDS,
  CHART_LIMITS,
  CHART_THEME,
  formatTND,
} from "@/lib/dashboardConstants";
import { useFilters } from "@/store/useFilters";
import { useMemo, useState } from "react";import { api } from "@/lib/api";
import { useApiResource } from "@/hooks/useApiResource";

export const Route = createFileRoute("/comptabilite")({
  component: ComptabilitePage,
});

function AnomalyDot(props) {
  const { cx, cy, payload } = props;
  if (payload?.anomalie) {
    return (
      <circle
        cx={cx}
        cy={cy}
        r={6}
        fill={CHART_THEME.negative}
        stroke={CHART_THEME.negative}
        strokeWidth={3}
        opacity={0.9}
      />
    );
  }
  return (
    <circle cx={cx} cy={cy} r={3} fill={CHART_THEME.primary} opacity={0.4} />
  );
}

const BUCKET_COLORS = {
  "0-30j":  "#22c55e",
  "31-60j": "#f59e0b",
  "61-90j": "#94a3b8",
  ">90j":   "#ef4444",
};
const BUCKET_LABELS = {
  "0-30j": "0–30j", "31-60j": "31–60j", "61-90j": "61–90j", ">90j": ">90j",
};
const BUCKETS = ["0-30j", "31-60j", "61-90j", ">90j"];

function AgingTotalBar({ row }) {
  const total = BUCKETS.reduce((s, b) => s + (row[b] || 0), 0);
  if (total === 0) return null;
  return (
    <div style={{ display: "flex", height: 6, borderRadius: 3, overflow: "hidden", width: "100%", minWidth: 80 }}>
      {BUCKETS.map(b => {
        const pct = (row[b] || 0) / total * 100;
        if (pct === 0) return null;
        return <div key={b} style={{ width: `${pct}%`, background: BUCKET_COLORS[b] }} />;
      })}
    </div>
  );
}

function AgingChart({ chartsLoading, chartH, paretoData, restAgingData }) {
  const [expanded, setExpanded] = useState(false);
  const fmtK = (v) => v >= 1000 ? `${(v/1000).toFixed(0)}K` : v.toFixed(0);
  return (
    <ChartCard loading={chartsLoading} skeleton="bar" title="Répartition des créances par ancienneté">
      <ResponsiveContainer width="100%" height={chartH}>
        <BarChart data={paretoData} margin={{ top: 10, right: 20, left: 0, bottom: 20 }}>
          <CartesianGrid stroke={CHART_THEME.grid} strokeDasharray="3 3" />
          <XAxis dataKey="client" tick={{ fill: CHART_THEME.axis, fontSize: 9 }} axisLine={false} angle={-45} textAnchor="end" interval={0} height={60} tickFormatter={(v) => v.length > 15 ? v.slice(0, 15) + "…" : v} />
          <YAxis tick={{ fill: CHART_THEME.axis, fontSize: 10 }} axisLine={false} tickFormatter={(v) => v >= 1000000 ? `${(v/1000000).toFixed(1)}M` : `${(v/1000).toFixed(0)}K`} />
          <Tooltip content={<CustomTooltip />} />
          {/* remove Legend from inside BarChart */}
          <Bar dataKey="0-30j"  stackId="age" fill={CHART_THEME.positive} name="0 à 30 jours" />
          <Bar dataKey="31-60j" stackId="age" fill={CHART_THEME.warning}  name="31 à 60 jours" />
          <Bar dataKey="61-90j" stackId="age" fill={CHART_THEME.neutral}  name="61 à 90 jours" />
          <Bar dataKey=">90j"   stackId="age" fill={CHART_THEME.negative} name="Plus de 90 jours" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <div style={{ display: "flex", justifyContent: "center", gap: 16, flexWrap: "wrap", fontSize: 11, color: CHART_THEME.muted, marginTop: 6, marginBottom: 4 }}>
        {[["0-30j","#22c55e","0 à 30 jours"],["31-60j","#f59e0b","31 à 60 jours"],["61-90j","#94a3b8","61 à 90 jours"],[">90j","#ef4444","Plus de 90 jours"]].map(([,color,label]) => (
          <span key={label} style={{ display: "flex", alignItems: "center", gap: 4 }}>
            <span style={{ width: 10, height: 10, borderRadius: 2, background: color, display: "inline-block" }} />
            {label}
          </span>
        ))}
      </div>

      {restAgingData.length > 0 && (
        <div style={{ marginTop: 16, borderTop: "1px solid var(--color-border-tertiary)", paddingTop: 12 }}>
          <button
            onClick={() => setExpanded(e => !e)}
            style={{
              display: "inline-flex", alignItems: "center", gap: 6,
              background: "var(--color-bg-secondary, #f1f5f9)", border: "1px solid var(--color-border-tertiary)",
              borderRadius: 6, cursor: "pointer", color: "var(--color-text-secondary)",
              fontSize: 12, padding: "6px 12px", width: "auto",
            }}
          >
            <i className={`ti ti-chevron-${expanded ? "up" : "down"}`} style={{ fontSize: 14 }} />
            {expanded ? "Masquer" : `Voir ${restAgingData.length} autres clients`}
          </button>

          {expanded && (
            <div style={{ marginTop: 8, overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 11 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--color-border-tertiary)" }}>
                    <th style={{ textAlign: "left", padding: "4px 8px", color: "var(--color-text-secondary)", fontWeight: 500 }}>Client</th>
                    {BUCKETS.map(b => (
                      <th key={b} style={{ textAlign: "right", padding: "4px 8px", color: BUCKET_COLORS[b], fontWeight: 500 }}>{BUCKET_LABELS[b]}</th>
                    ))}
                    <th style={{ textAlign: "right", padding: "4px 8px", color: "var(--color-text-secondary)", fontWeight: 500 }}>Total</th>
                    <th style={{ padding: "4px 8px", width: 100, textAlign: "center", color: "var(--color-text-secondary)", fontWeight: 500 }}>Répartition</th>
                  </tr>
                </thead>
                <tbody>
                  {restAgingData.map((row, i) => {
                    const total = BUCKETS.reduce((s, b) => s + (row[b] || 0), 0);
                    return (
                      <tr key={i} style={{ borderBottom: "1px solid var(--color-border-tertiary)", background: i % 2 === 0 ? "transparent" : "var(--color-bg-secondary, #f8fafc)" }}>
                        <td style={{ padding: "5px 8px", color: "var(--color-text-primary)", maxWidth: 180, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{row.client}</td>
                        {BUCKETS.map(b => (
                          <td key={b} style={{ textAlign: "right", padding: "5px 8px", color: row[b] > 0 ? BUCKET_COLORS[b] : "var(--color-text-tertiary)", fontWeight: row[b] > 0 ? 500 : 400 }}>
                            {row[b] > 0 ? fmtK(row[b]) : "—"}
                          </td>
                        ))}
                        <td style={{ textAlign: "right", padding: "5px 8px", color: "var(--color-text-primary)", fontWeight: 500 }}>{fmtK(total)}</td>
                        <td style={{ padding: "5px 8px" }}><AgingTotalBar row={row} /></td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </ChartCard>
  );
}

function ComptabilitePage() {
  const { year, quarter } = useFilters();
  const chartH = useChartHeight();

  const summaryFn = useMemo(
    () => () => api.tresorerie.summary(),
    [year, quarter],
  );
  const agingFn = useMemo(() => () => api.tresorerie.aging(), [year, quarter]);
  const fiscKpisFn = useMemo(() => () => api.fiscalite.kpis(), [year, quarter]);
  const tvaDataFn = useMemo(
    () => () => api.fiscalite.tvaByMonth(),
    [year, quarter],
  );
  const anomalyDataFn = useMemo(
    () => () => api.fiscalite.anomalies(),
    [year, quarter],
  );

  // ── Trésorerie data ──
  const { data: summary, loading: summaryLoading } = useApiResource(summaryFn, {
    encaissements: 0,
    impayes: 0,
    delai_moyen: 0,
    taux_recouvrement: 0,
  });
  const { data: agingData, loading: agingLoading } = useApiResource(
    agingFn,
    [],
  );

  // ── Fiscalité data ──
  const { data: fiscKpis, loading: fiscLoading } = useApiResource(fiscKpisFn, {
    nb_ecritures: 0,
    tva_collectee: 0,
    tva_deductible: 0,
    anomalies: 0,
    equilibre_pct: 0,
  });
  const { data: tvaData, loading: tvaLoading } = useApiResource(tvaDataFn, []);
  const { data: anomalyData, loading: anomaliesLoading } = useApiResource(
    anomalyDataFn,
    [],
  );

  const kpiLoading = summaryLoading || fiscLoading;
  const chartsLoading =
    summaryLoading || agingLoading || tvaLoading || anomaliesLoading;

  const safeAgingData = useMemo(
    () =>
      (Array.isArray(agingData) ? agingData : [])
        .filter(Boolean)
        .map((row) => ({
          client: row.client || "Client",
          "0-30j": Number(row["0-30j"]) || 0,
          "31-60j": Number(row["31-60j"]) || 0,
          "61-90j": Number(row["61-90j"]) || 0,
          ">90j": Number(row[">90j"]) || 0,
        })),
    [agingData],
  );

  const gt90 = safeAgingData.reduce((sum, row) => sum + row[">90j"], 0);

const AGING_LIMIT = 15;
const sortedAgingData = useMemo(() =>
  [...safeAgingData]
    .filter(row => row[">90j"] > 0 || row["61-90j"] > 0 || row["31-60j"] > 0 || row["0-30j"] > 0)
    .sort((a, b) => b[">90j"] - a[">90j"]),
  [safeAgingData]
);
const paretoData = useMemo(() => sortedAgingData.slice(0, AGING_LIMIT), [sortedAgingData]);
const restAgingData = useMemo(() => sortedAgingData.slice(AGING_LIMIT), [sortedAgingData]);

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
              value={`${(fiscKpis?.equilibre_pct ?? 0).toFixed(2)}%`}
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
        <span className="text-[11px] font-bold uppercase tracking-widest text-text-dim">
          Trésorerie
        </span>
        <div className="flex-1 h-px bg-border/30" />
      </div>
      <div className="grid grid-cols-1 gap-4">
        <AgingChart
          chartsLoading={chartsLoading}
          chartH={chartH}
          paretoData={paretoData}
          restAgingData={restAgingData}
        />
      </div>

      {/* Section Fiscalité */}
      <div className="flex items-center gap-3">
        <span className="text-[11px] font-bold uppercase tracking-widest text-text-dim">
          Fiscalité
        </span>
        <div className="flex-1 h-px bg-border/30" />
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard
          loading={chartsLoading}
          skeleton="bar"
          title="TVA collectée et TVA déductible"
        >
          <ResponsiveContainer width="100%" height={chartH - 40}>
            <ComposedChart data={tvaData}>
              <CartesianGrid stroke={CHART_THEME.grid} strokeDasharray="3 3" />
              <XAxis
                dataKey="month"
                tick={{ fill: CHART_THEME.axis, fontSize: 11 }}
                axisLine={false}
              />
              <YAxis
                yAxisId="left"
                tick={{ fill: CHART_THEME.axis, fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend
                wrapperStyle={{ fontSize: 12, color: CHART_THEME.muted }}
              />
              <Bar
                yAxisId="left"
                dataKey="soldeNet"
                fill={CHART_THEME.positive}
                opacity={0.4}
                radius={[4, 4, 0, 0]}
                name="Solde net TVA"
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="collectee"
                stroke={CHART_THEME.primary}
                strokeWidth={2}
                dot={false}
                name="TVA collectée"
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="deductible"
                stroke={CHART_THEME.negative}
                strokeWidth={2}
                dot={false}
                name="TVA déductible"
              />
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          loading={chartsLoading}
          skeleton="scatter"
          title="Détection anomalies comptables"
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <ScatterChart margin={{ top: 10, right: 10, bottom: 20, left: 10 }}>
              <CartesianGrid stroke={CHART_THEME.grid} strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                name="Date"
                type="category"
                tick={{ fill: CHART_THEME.axis, fontSize: 9 }}
                axisLine={false}
                angle={-30}
                textAnchor="end"
                height={40}
              />
              <YAxis
                dataKey="score"
                name="Score anomalie"
                tick={{ fill: CHART_THEME.axis, fontSize: 11 }}
                axisLine={false}
                domain={[CHART_LIMITS.scoreMin, CHART_LIMITS.scoreMax]}
                label={{
                  value: "Score (0-1)",
                  angle: -90,
                  position: "insideLeft",
                  fill: CHART_THEME.axis,
                  fontSize: 10,
                }}
              />
              <ZAxis
                dataKey="montant"
                range={[
                  CHART_LIMITS.anomalyBubbleMin,
                  CHART_LIMITS.anomalyBubbleMax,
                ]}
                name="Montant"
              />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine
                y={BUSINESS_THRESHOLDS.anomalyScore}
                stroke={CHART_THEME.negative}
                strokeDasharray="4 4"
                label={{
                  value: `Seuil ${BUSINESS_THRESHOLDS.anomalyScore}`,
                  fill: CHART_THEME.negative,
                  fontSize: 10,
                  position: "right",
                }}
              />
              <Scatter data={anomalyData} shape={AnomalyDot} name="Écriture" />
            </ScatterChart>
          </ResponsiveContainer>
          <p className="text-[10px] text-text-dim mt-1 text-right">
            <span className="inline-flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-red-500 inline-block" />
              {(fiscKpis?.anomalies ?? 0).toLocaleString("fr-TN")} anomalies
              (score &gt;= {BUSINESS_THRESHOLDS.anomalyScore})
            </span>
          </p>
        </ChartCard>
      </div>
    </div>
  );
}
