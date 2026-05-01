import { createFileRoute } from "@tanstack/react-router";
import { KPICard } from "@/components/dashboard/KPICard";
import { KPICardSkeleton, useChartHeight, ChartCard, useSimulatedLoading } from "@/components/dashboard/ChartCard";
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
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
} from "recharts";
import { ecritures, MONTHS, formatTND } from "@/data/mockData";

export const Route = createFileRoute("/ecritures")({
  component: EcrituresPage,
});

// Top 10 journaux grouped Débit/Crédit (KPI-25/27)
const journaux = ["Ventes", "Achats", "Banque", "Caisse", "OD", "Salaires", "TVA", "Immob.", "Clients", "Fournisseurs"];
const journalData = journaux.map((j) => ({
  journal: j,
  debit: Math.round(100000 + Math.random() * 500000),
  credit: Math.round(100000 + Math.random() * 500000),
}));

// TVA dual-line (KPI-26)
const tvaData = MONTHS.map((m) => ({
  month: m,
  collectee: Math.round(120000 + Math.random() * 80000),
  deductible: Math.round(30000 + Math.random() * 40000),
  soldeNet: 0,
}));
tvaData.forEach((d) => { d.soldeNet = d.collectee - d.deductible; });

// Anomaly scatter (KPI-28) — Isolation Forest scores
const anomalyData = Array.from({ length: 80 }, (_, i) => {
  const date = `2024-${String(Math.ceil(Math.random() * 12)).padStart(2, "0")}-${String(Math.ceil(Math.random() * 28)).padStart(2, "0")}`;
  const score = Math.random();
  return {
    date,
    score: parseFloat(score.toFixed(3)),
    montant: Math.round(10000 + Math.random() * 200000),
    journal: ["Ventes", "Achats", "Banque", "OD"][Math.floor(Math.random() * 4)],
    anomalie: score > 0.8,
  };
});

// Waterfall mensuel débit/crédit (KPI-25)
const waterfallData = MONTHS.map((m) => {
  const debit = Math.round(200000 + Math.random() * 400000);
  const credit = Math.round(200000 + Math.random() * 400000);
  return { month: m, debit, credit, ecart: debit - credit };
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

// Custom dot for anomaly scatter
function AnomalyDot(props) {
  const { cx, cy, payload } = props;
  if (payload.anomalie) {
    return <circle cx={cx} cy={cy} r={6} fill="#ef4444" stroke="#ff000044" strokeWidth={3} opacity={0.9} />;
  }
  return <circle cx={cx} cy={cy} r={3} fill="#3b82f6" opacity={0.4} />;
}

function EcrituresPage() {
  const nbAnomalies = anomalyData.filter((d) => d.anomalie).length;
  const chartH = useChartHeight();
  const kpiLoading    = useSimulatedLoading(500);
  const chartsLoading = useSimulatedLoading(950);

  return (
    <div className="space-y-6">
      {/* KPI Cards */}
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
            <KPICard label="Écritures comptables" value="663 138" subtitle="32 journaux — 5 exercices" icon={FileText} />
            <KPICard label="TVA collectée YTD" value="1.8 MDT" subtitle="vs 0.4 MDT déductible" icon={Receipt} />
            <KPICard label="Anomalies détectées" value={String(nbAnomalies)} subtitle="Isolation Forest — mois" trend={-2} icon={AlertCircle} />
            <KPICard label="Équilibre débit/crédit" value="98.4%" subtitle="écarts < 0.01 DT" icon={CheckCircle} />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Widget A: Grouped bar Débit vs Crédit top 10 journaux (KPI-25/27) */}
        <ChartCard title="Soldes par journal — Débit vs Crédit (KPI-25/27)" loading={chartsLoading} skeleton="bar">
          <ResponsiveContainer width="100%" height={chartH}>
            <BarChart data={journalData}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="journal" tick={{ fill: "#666", fontSize: 10 }} axisLine={false} angle={-20} textAnchor="end" height={40} />
              <YAxis tick={{ fill: "#666", fontSize: 11 }} axisLine={false} tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#888" }} />
              <Bar dataKey="debit" fill="#3b82f6" radius={[4, 4, 0, 0]} name="Débit" />
              <Bar dataKey="credit" fill="#6366f1" radius={[4, 4, 0, 0]} name="Crédit" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Widget B: TVA dual-line (KPI-26) */}
        <ChartCard title="TVA collectée vs déductible (KPI-26)" loading={chartsLoading} skeleton="bar">
          <ResponsiveContainer width="100%" height={chartH}>
            <BarChart data={tvaData}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="month" tick={{ fill: "#666", fontSize: 11 }} axisLine={false} />
              <YAxis yAxisId="left" tick={{ fill: "#666", fontSize: 11 }} axisLine={false} tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
              <YAxis yAxisId="right" orientation="right" tick={{ fill: "#22c55e", fontSize: 11 }} axisLine={false} tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#888" }} />
              <Bar yAxisId="left" dataKey="soldeNet" fill="#22c55e" opacity={0.4} radius={[4, 4, 0, 0]} name="Solde net TVA" />
              <Line yAxisId="left" type="monotone" data={tvaData} dataKey="collectee" stroke="#3b82f6" strokeWidth={2} dot={false} name="TVA collectée" />
              <Line yAxisId="left" type="monotone" data={tvaData} dataKey="deductible" stroke="#ef4444" strokeWidth={2} dot={false} name="TVA déductible" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Widget C: Anomaly scatter (KPI-28) */}
        <ChartCard title="Détection anomalies comptables — Isolation Forest (KPI-28)" loading={chartsLoading} skeleton="scatter">
          <ResponsiveContainer width="100%" height={chartH}>
            <ScatterChart margin={{ top: 10, right: 10, bottom: 20, left: 10 }}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="date" name="Date" tick={{ fill: "#666", fontSize: 9 }} axisLine={false} angle={-30} textAnchor="end" height={40} />
              <YAxis dataKey="score" name="Score anomalie" tick={{ fill: "#666", fontSize: 11 }} axisLine={false} domain={[0, 1]} label={{ value: "Score (0-1)", angle: -90, position: "insideLeft", fill: "#555", fontSize: 10 }} />
              <ZAxis dataKey="montant" range={[30, 300]} name="Montant" />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine y={0.8} stroke="#ef4444" strokeDasharray="4 4" label={{ value: "Seuil 0.8", fill: "#ef4444", fontSize: 10, position: "right" }} />
              <Scatter data={anomalyData} shape={<AnomalyDot />} name="Écriture" />
            </ScatterChart>
          </ResponsiveContainer>
          <p className="text-[10px] text-text-dim mt-1 text-right">
            <span className="inline-flex items-center gap-1"><span className="w-2 h-2 rounded-full bg-red-500 inline-block" /> {nbAnomalies} anomalies (score &gt; 0.8)</span>
          </p>
        </ChartCard>

        {/* Widget D: Waterfall mensuel débit/crédit (KPI-25) */}
        <ChartCard title="Équilibre comptable mensuel — Waterfall (KPI-25)" loading={chartsLoading} skeleton="bar">
          <ResponsiveContainer width="100%" height={chartH}>
            <BarChart data={waterfallData}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="month" tick={{ fill: "#666", fontSize: 11 }} axisLine={false} />
              <YAxis tick={{ fill: "#666", fontSize: 11 }} axisLine={false} tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#888" }} />
              <ReferenceLine y={0} stroke="#555" />
              <Bar dataKey="debit" fill="#3b82f6" name="Débit" radius={[4, 4, 0, 0]} opacity={0.8} />
              <Bar dataKey="credit" fill="#6366f1" name="Crédit" radius={[4, 4, 0, 0]} opacity={0.8} />
              <Bar
                dataKey="ecart"
                name="Écart D-C"
                radius={[4, 4, 0, 0]}
                fill="#22c55e"
                label={false}
              >
                {waterfallData.map((d, i) => (
                  <rect key={i} fill={d.ecart >= 0 ? "#22c55e" : "#ef4444"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>

      <DataTable data={ecritures} columns={columns} />
    </div>
  );
}