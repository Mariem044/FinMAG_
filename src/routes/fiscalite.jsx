import { createFileRoute } from "@tanstack/react-router";
import { KPICard } from "@/components/dashboard/KPICard";
import { useChartHeight, ChartCard, KPICardSkeleton } from "@/components/dashboard/ChartCard";
import { CustomTooltip } from "@/components/dashboard/CustomTooltip";
import { DataTable } from "@/components/dashboard/DataTable";
import { FileText, Receipt, AlertCircle, CheckCircle } from "lucide-react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  ScatterChart,
  Scatter,
  ComposedChart,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  ZAxis,
  Cell,
} from "recharts";
import { formatPercent, formatTND } from "@/lib/dashboardConstants";
import { api } from "@/lib/api";
import { useApiResource } from "@/hooks/useApiResource";

export const Route = createFileRoute("/fiscalite")({
  component: FiscalitePage,
});

const columns = [
  { accessorKey: "date", header: "Date" },
  { accessorKey: "numPiece", header: "N° Pièce" },
  { accessorKey: "journal", header: "Journal" },
  { accessorKey: "compte", header: "Compte" },
  { accessorKey: "libelle", header: "Libellé" },
  { accessorKey: "debit", header: "Débit", cell: ({ getValue }) => formatTND(getValue()) },
  { accessorKey: "credit", header: "Crédit", cell: ({ getValue }) => formatTND(getValue()) },
  {
    accessorKey: "solde",
    header: "Solde",
    cell: ({ getValue }) => {
      const v = getValue();
      return <span className={v >= 0 ? "text-trend-up" : "text-trend-down"}>{formatTND(v)}</span>;
    },
  },
];

function AnomalyDot(props) {
  const { cx, cy, payload } = props;
  if (payload?.anomalie) {
    return (
      <circle
        cx={cx}
        cy={cy}
        r={6}
        fill="#ef4444"
        stroke="#ff000044"
        strokeWidth={3}
        opacity={0.9}
      />
    );
  }
  return <circle cx={cx} cy={cy} r={3} fill="#3b82f6" opacity={0.4} />;
}

function FiscalitePage() {
  const { data: kpis, loading: kpisLoading } = useApiResource(api.fiscalite.kpis, {
    nb_ecritures: 0,
    tva_collectee: 0,
    tva_deductible: 0,
    anomalies: 0,
    equilibre_pct: 0,
  });
  const { data: journalData, loading: journauxLoading } = useApiResource(
    api.fiscalite.journaux,
    [],
  );
  const { data: tvaData, loading: tvaLoading } = useApiResource(api.fiscalite.tvaByMonth, []);
  const { data: anomalyData, loading: anomaliesLoading } = useApiResource(
    api.fiscalite.anomalies,
    [],
  );
  const { data: waterfallData, loading: balanceLoading } = useApiResource(
    api.fiscalite.balanceByMonth,
    [],
  );
  const { data: ecritures, loading: ecrituresLoading } = useApiResource(
    api.fiscalite.ecritures,
    [],
  );

  const nbAnomalies = Array.isArray(anomalyData)
    ? anomalyData.filter((d) => d?.anomalie).length
    : 0;
  const chartH = useChartHeight();
  const kpiLoading = kpisLoading;
  const chartsLoading =
    journauxLoading || tvaLoading || anomaliesLoading || balanceLoading || ecrituresLoading;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {kpiLoading ? (
          <>
            <KPICardSkeleton />
            <KPICardSkeleton />
            <KPICardSkeleton />
            <KPICardSkeleton />
          </>
        ) : (
          <>
            <KPICard
              label="Écritures comptables"
              value={(kpis?.nb_ecritures || 0).toLocaleString("fr-TN")}
              subtitle={`${journalData?.length || 0} journaux`}
              icon={FileText}
            />
            <KPICard
              label="TVA collectée YTD"
              value={formatTND(kpis?.tva_collectee || 0)}
              subtitle={`vs ${formatTND(kpis?.tva_deductible || 0)} déductible`}
              icon={Receipt}
            />
            <KPICard
              label="Anomalies détectées"
              value={String(kpis?.anomalies || nbAnomalies)}
              subtitle="Score issu du DW"
              trend={-2}
              icon={AlertCircle}
            />
            <KPICard
              label="Équilibre débit/crédit"
              value={formatPercent(kpis?.equilibre_pct || 0)}
              subtitle="Débit / crédit"
              icon={CheckCircle}
            />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard
          loading={chartsLoading}
          skeleton="bar"
          title="Soldes par journal — Débit vs Crédit (KPI-19)"
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <BarChart data={journalData}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis
                dataKey="journal"
                tick={{ fill: "#666", fontSize: 10 }}
                axisLine={false}
                angle={-20}
                textAnchor="end"
                height={40}
              />
              <YAxis
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#888" }} />
              <Bar dataKey="debit" fill="#3b82f6" radius={[4, 4, 0, 0]} name="Débit" />
              <Bar dataKey="credit" fill="#6366f1" radius={[4, 4, 0, 0]} name="Crédit" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard
          loading={chartsLoading}
          skeleton="bar"
          title="TVA collectée vs déductible (KPI-20)"
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <ComposedChart data={tvaData}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="month" tick={{ fill: "#666", fontSize: 11 }} axisLine={false} />
              <YAxis
                yAxisId="left"
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <YAxis
                yAxisId="right"
                orientation="right"
                tick={{ fill: "#22c55e", fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#888" }} />
              <Bar
                yAxisId="left"
                dataKey="soldeNet"
                fill="#22c55e"
                opacity={0.4}
                radius={[4, 4, 0, 0]}
                name="Solde net TVA"
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="collectee"
                stroke="#3b82f6"
                strokeWidth={2}
                dot={false}
                name="TVA collectée"
              />
              <Line
                yAxisId="left"
                type="monotone"
                dataKey="deductible"
                stroke="#ef4444"
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
          title="Détection anomalies comptables — score local (KPI-21)"
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <ScatterChart margin={{ top: 10, right: 10, bottom: 20, left: 10 }}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis
                dataKey="date"
                name="Date"
                tick={{ fill: "#666", fontSize: 9 }}
                axisLine={false}
                angle={-30}
                textAnchor="end"
                height={40}
              />
              <YAxis
                dataKey="score"
                name="Score anomalie"
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                domain={[0, 1]}
                label={{
                  value: "Score (0-1)",
                  angle: -90,
                  position: "insideLeft",
                  fill: "#555",
                  fontSize: 10,
                }}
              />
              <ZAxis dataKey="montant" range={[30, 300]} name="Montant" />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine
                y={0.8}
                stroke="#ef4444"
                strokeDasharray="4 4"
                label={{ value: "Seuil 0.8", fill: "#ef4444", fontSize: 10, position: "right" }}
              />
              <Scatter data={anomalyData} shape={<AnomalyDot />} name="Écriture" />
            </ScatterChart>
          </ResponsiveContainer>
          <p className="text-[10px] text-text-dim mt-1 text-right">
            <span className="inline-flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-red-500 inline-block" />
              {nbAnomalies} anomalies (score &gt; 0.8)
            </span>
          </p>
        </ChartCard>

        <ChartCard
          loading={chartsLoading}
          skeleton="bar"
          title="Équilibre comptable mensuel — Waterfall (KPI-19)"
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <ComposedChart data={waterfallData}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="month" tick={{ fill: "#666", fontSize: 11 }} axisLine={false} />
              <YAxis
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#888" }} />
              <ReferenceLine y={0} stroke="#555" />
              <Bar
                dataKey="debit"
                fill="#3b82f6"
                name="Débit"
                radius={[4, 4, 0, 0]}
                opacity={0.8}
              />
              <Bar
                dataKey="credit"
                fill="#6366f1"
                name="Crédit"
                radius={[4, 4, 0, 0]}
                opacity={0.8}
              />
              <Bar dataKey="ecart" name="Écart D-C" radius={[4, 4, 0, 0]}>
                {(waterfallData || []).map((d, i) => (
                  <Cell key={i} fill={d?.ecart >= 0 ? "#22c55e" : "#ef4444"} />
                ))}
              </Bar>
            </ComposedChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <DataTable data={ecritures || []} columns={columns} />
    </div>
  );
}
