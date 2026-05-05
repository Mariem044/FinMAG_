import { createFileRoute } from "@tanstack/react-router";
import { KPICard } from "@/components/dashboard/KPICard";
import { useChartHeight, ChartCard, useSimulatedLoading, KPICardSkeleton } from "@/components/dashboard/ChartCard";
import { CustomTooltip } from "@/components/dashboard/CustomTooltip";
import { Landmark, CheckCircle, Receipt, Clock } from "lucide-react";
import {
  BarChart, Bar, LineChart, Line,
  XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, ReferenceLine, Cell,
} from "recharts";
import { MONTHS, CHART_COLORS } from "@/data/mockData";
import { useFilters } from "@/store/useFilters";
import { useMemo } from "react";

export const Route = createFileRoute("/banque")({
  component: BanquePage,
});

const ALL_BANQUES = ["AMEN", "ZITOUNA", "QNB", "BT"];
const ALL_MODES   = ["Chèque", "Traite", "Virement"];
const priorityColor = { Chèque: "#3b82f6", Traite: "#ef4444", Virement: "#22c55e" };

// Base rapprochement data
const BASE_RAPPROCH = MONTHS.map((m) => ({
  month: m,
  taux: Math.round(88 + Math.random() * 9),
  nonRapproches: Math.round(5 + Math.random() * 30),
}));

function GaugeRapprochement({ value }) {
  const pct = value / 100;
  const r = 65, cx = 90, cy = 80;
  const startA = Math.PI, endA = 0;
  const valA = startA + (endA - startA) * pct;
  const arc = (a, rr) => ({ x: cx + rr * Math.cos(a), y: cy + rr * Math.sin(a) });
  const bg   = `M ${arc(startA, r).x} ${arc(startA, r).y} A ${r} ${r} 0 0 1 ${arc(endA, r).x} ${arc(endA, r).y}`;
  const fill = `M ${arc(startA, r).x} ${arc(startA, r).y} A ${r} ${r} 0 ${pct > 0.5 ? 1 : 0} 1 ${arc(valA, r).x} ${arc(valA, r).y}`;
  const color = value >= 95 ? "#22c55e" : value >= 90 ? "#f97316" : "#ef4444";
  return (
    <svg width={180} height={100}>
      <path d={bg}   fill="none" stroke="#2a2a2a" strokeWidth={13} strokeLinecap="round" />
      <path d={fill} fill="none" stroke={color}   strokeWidth={13} strokeLinecap="round" />
      <line x1={cx} y1={cy} x2={arc(valA, r - 16).x} y2={arc(valA, r - 16).y} stroke={color} strokeWidth={2} strokeLinecap="round" />
      <circle cx={cx} cy={cy} r={4} fill={color} />
      <text x={cx} y={cy - 14} textAnchor="middle" fill={color} fontSize={24} fontWeight="bold">{value}%</text>
      <text x={cx} y={cy + 2}  textAnchor="middle" fill="#666" fontSize={10}>taux rapprochement</text>
    </svg>
  );
}

function GanttPipeline({ data }) {
  return (
    <div className="overflow-auto">
      <div className="flex gap-1 text-[9px] text-text-dim mb-2 ml-24">
        {Array.from({ length: 30 }, (_, i) => (
          <div key={i} className="w-4 text-center flex-shrink-0">{i + 1}</div>
        ))}
      </div>
      {data.map((row, i) => {
        const barStart = ((row.echeance - 1) / 30) * 100;
        const barWidth = Math.max(3, 100 / 30);
        return (
          <div key={i} className="flex items-center gap-2 mb-1.5">
            <div className="w-24 flex-shrink-0 text-[10px]">
              <span className="font-medium text-foreground">{row.banque}</span>
              <span className="text-text-dim ml-1">{row.mode}</span>
            </div>
            <div className="flex-1 relative h-5 bg-surface-hover/40 rounded">
              <div
                className="absolute top-0.5 h-4 rounded flex items-center px-1 text-[9px] text-white font-medium"
                style={{ left: `${barStart}%`, width: `${barWidth}%`, minWidth: 48, background: priorityColor[row.mode] || "#3b82f6", opacity: 0.85 }}
              >
                {(row.montant / 1000).toFixed(0)}K
              </div>
            </div>
            <span className="text-[10px] text-text-dim w-8 text-right">J+{row.echeance}</span>
          </div>
        );
      })}
      <div className="flex gap-3 text-[10px] text-text-dim mt-2">
        {Object.entries(priorityColor).map(([k, c]) => (
          <span key={k} className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-sm inline-block" style={{ background: c }} /> {k}
          </span>
        ))}
      </div>
    </div>
  );
}

function BanquePage() {
  const { banque, modeBanque, getActiveMonthIndexes } = useFilters();
  const activeIdx = getActiveMonthIndexes();
  const chartH = useChartHeight();
  const kpiLoading    = useSimulatedLoading(500);
  const chartsLoading = useSimulatedLoading(950);

  const activeBanques = useMemo(() =>
    banque === "Toutes" ? ALL_BANQUES : [banque],
    [banque]
  );
  const activeModes = useMemo(() =>
    modeBanque === "Tous" ? ALL_MODES : [modeBanque],
    [modeBanque]
  );

  // Bordereau data filtered by banque and mode
  const banqueMode = useMemo(() =>
    activeBanques.map((b) => {
      const row = { banque: b };
      activeModes.forEach((mo) => {
        row[mo] = Math.round(200000 + Math.random() * 800000);
      });
      return row;
    }),
    [activeBanques, activeModes]
  );

  // Rapprochement filtered by banque and months
  const rapprochData = useMemo(() =>
    BASE_RAPPROCH.filter((_, i) => activeIdx.includes(i)),
    [activeIdx]
  );

  // Current taux — average if multiple banks
  const currentTaux = rapprochData.length > 0
    ? Math.round(rapprochData.reduce((s, d) => s + d.taux, 0) / rapprochData.length)
    : 94;

  // Agios filtered by banque
  const agiosData = useMemo(() =>
    Array.from({ length: 12 }, (_, i) => ({
      bordereau:  `BR-${String(i + 1).padStart(3, "0")}`,
      banque:     activeBanques[i % activeBanques.length],
      agios:      Math.round(200 + Math.random() * 1500),
      nbJour:     Math.round(2 + Math.random() * 8),
      tauxAgios:  parseFloat((2 + Math.random() * 3).toFixed(2)),
    })),
    [activeBanques]
  );

  const totalAgios = agiosData.reduce((s, d) => s + d.agios, 0);
  const floatMoyen = parseFloat((agiosData.reduce((s, d) => s + d.nbJour, 0) / agiosData.length).toFixed(1));

  // Non rapprochés
  const nonRapproches = useMemo(() =>
    Array.from({ length: 10 }, (_, i) => ({
      reference: `RGL-2024-${String(i + 1).padStart(4, "0")}`,
      banque:    activeBanques[i % activeBanques.length],
      montant:   Math.round(10000 + Math.random() * 200000),
      ecart:     Math.round(Math.random() * 1000),
    })),
    [activeBanques]
  );

  // Gantt pipeline filtered by mode and banque
  const pipelineRemises = useMemo(() =>
    Array.from({ length: 14 }, (_, i) => ({
      id:       `REM-${String(i + 1).padStart(3, "0")}`,
      banque:   activeBanques[i % activeBanques.length],
      mode:     activeModes[i % activeModes.length],
      montant:  Math.round(50000 + Math.random() * 400000),
      echeance: i + 1,
    })).sort((a, b) => a.echeance - b.echeance),
    [activeBanques, activeModes]
  );

  // Total remis
  const totalRemis = banqueMode.reduce((s, b) => {
    return s + activeModes.reduce((ms, m) => ms + (b[m] || 0), 0);
  }, 0);

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
      <KPICard label="Total remis en banque" value={`${(totalRemis / 1000000).toFixed(1)} MDT`} subtitle={banque !== "Toutes" ? banque : "4 banques"} icon={Landmark} />
      <KPICard label="Taux rapprochement" value={`${currentTaux}%`} trend={1.8} icon={CheckCircle} />
      <KPICard label="Agios & frais bancaires" value={`${totalAgios.toLocaleString("fr-TN")} DT`} subtitle="cumulé période" icon={Receipt} />
      <KPICard label="Float bancaire moyen" value={`${floatMoyen}j`} subtitle="LB_NbJour AVG" icon={Clock} />
    </>
  )}
</div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard loading={chartsLoading} skeleton="bar" key={`${banque}-${modeBanque}-${activeIdx.join("")}`} title={`Bordereaux${banque !== "Toutes" ? ` — ${banque}` : " par banque"}${modeBanque !== "Tous" ? ` — ${modeBanque}` : ""} (KPI-25)`}>
          <ResponsiveContainer width="100%" height={chartH}>
            <BarChart data={banqueMode}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="banque" tick={{ fill: "#666", fontSize: 12 }} axisLine={false} />
              <YAxis tick={{ fill: "#666", fontSize: 11 }} axisLine={false} tickFormatter={(v) => `${(v/1000).toFixed(0)}K`} />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#888" }} />
              {activeModes.map((m, i) => (
                <Bar key={m} dataKey={m} stackId="mode" fill={priorityColor[m]} name={m}
                  radius={i === activeModes.length - 1 ? [4, 4, 0, 0] : [0, 0, 0, 0]} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard loading={chartsLoading} skeleton="line" title="Taux de rapprochement bancaire (KPI-26)">
          <div className="flex gap-4 h-[280px]">
            <div className="flex flex-col items-center pt-4 flex-shrink-0">
              <GaugeRapprochement value={currentTaux} />
              <div className="mt-2 space-y-1 w-full">
                <p className="text-[10px] text-text-dim font-semibold mb-1">Non rapprochés (top)</p>
                {nonRapproches.slice(0, 4).map((r, i) => (
                  <div key={i} className="flex justify-between text-[10px]">
                    <span className="text-text-dim">{r.banque} · {r.reference.slice(-4)}</span>
                    <span className="text-foreground font-medium">{(r.montant / 1000).toFixed(0)}K</span>
                  </div>
                ))}
              </div>
            </div>
            <div className="flex-1">
              <ResponsiveContainer width="100%" height={180}>
                <LineChart data={rapprochData}>
                  <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
                  <XAxis dataKey="month" tick={{ fill: "#666", fontSize: 10 }} axisLine={false} />
                  <YAxis domain={[80, 100]} tick={{ fill: "#666", fontSize: 10 }} axisLine={false} tickFormatter={(v) => `${v}%`} />
                  <Tooltip content={<CustomTooltip />} />
                  <ReferenceLine y={95} stroke="#22c55e" strokeDasharray="3 3" label={{ value: "95%", fill: "#22c55e", fontSize: 9 }} />
                  <Line type="monotone" dataKey="taux" stroke="#3b82f6" strokeWidth={2} dot={{ r: 3 }} name="Taux rapproch." />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </ChartCard>

        <ChartCard loading={chartsLoading} skeleton="bar" title="Agios & Float bancaire (KPI-27)">
          <ResponsiveContainer width="100%" height={chartH}>
            <BarChart data={agiosData}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="bordereau" tick={{ fill: "#666", fontSize: 9 }} axisLine={false} angle={-30} textAnchor="end" height={40} />
              <YAxis yAxisId="left"  tick={{ fill: "#666",    fontSize: 11 }} axisLine={false} />
              <YAxis yAxisId="right" tick={{ fill: "#f97316", fontSize: 11 }} axisLine={false} orientation="right" />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 12, color: "#888" }} />
              <Bar yAxisId="left" dataKey="agios" name="Agios (DT)" radius={[4, 4, 0, 0]}>
                {agiosData.map((d, i) => (
                  <Cell key={i} fill={CHART_COLORS[ALL_BANQUES.indexOf(d.banque) % CHART_COLORS.length]} />
                ))}
              </Bar>
              <Line yAxisId="right" type="monotone" dataKey="nbJour" stroke="#f97316" strokeWidth={2} dot={{ r: 3 }} name="Float (j)" />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard loading={chartsLoading} skeleton="gantt" title={`Pipeline remises à venir 30j${modeBanque !== "Tous" ? ` — ${modeBanque}` : ""} (KPI-28)`}>
          <div className="pt-2 overflow-auto max-h-[280px]">
            <GanttPipeline data={pipelineRemises} />
          </div>
        </ChartCard>
      </div>
    </div>
  );
}