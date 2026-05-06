import { createFileRoute } from "@tanstack/react-router";
import { KPICard } from "@/components/dashboard/KPICard";
import { useChartHeight, ChartCard, useSimulatedLoading, KPICardSkeleton } from "@/components/dashboard/ChartCard";
import { CustomTooltip } from "@/components/dashboard/CustomTooltip";
import { Users, Building2, AlertTriangle, Truck } from "lucide-react"; 
import {
  ScatterChart, Scatter, BarChart, Bar,
  XAxis, YAxis, CartesianGrid, Tooltip,
  Legend, ResponsiveContainer, ZAxis,
  ReferenceLine, Cell,
} from "recharts";
import { clients, CHART_COLORS } from "@/data/mockData";
import { useFilters } from "@/store/useFilters";
import { useMemo } from "react";

export const Route = createFileRoute("/acteurs")({
  component: ActeursPage,
});

const rfmSegmentColors = {
  Champion: "#22c55e",
  Fidèle:   "#3b82f6",
  Risque:   "#f97316",
  Dormant:  "#ef4444",
};

const hhiData = [
  { article: "Biscuits Alpha",  hhi: 0.31, fournisseur: "Fournisseur A" },
  { article: "Boisson Beta",    hhi: 0.28, fournisseur: "Fournisseur C" },
  { article: "Conserve Gamma",  hhi: 0.19, fournisseur: "Fournisseur B" },
  { article: "Laitier Delta",   hhi: 0.42, fournisseur: "Fournisseur A" },
  { article: "Huile Epsilon",   hhi: 0.15, fournisseur: "Fournisseur D" },
];

// ── Stable seed data (generated once at module level, not inside useMemo) ──
const segmentKeys = Object.keys(rfmSegmentColors);

const RFM_SEED = clients.map((c, i) => ({
  code:      c.code,
  frequence: 1 + (i * 7 + 13) % 50,
  recence:   1 + (i * 11 + 7) % 180,
  montant:   c.caTotal,
  segment:   segmentKeys[i % segmentKeys.length],
  name:      c.nom,
}));

const AGING_SEED = clients.slice(0, 8).map((c, i) => ({
  clientCode: c.code,
  client:     c.nom.replace("Client ", "C"),
  "0-30j":    (i * 17 + 3)  % 80000,
  "31-60j":   (i * 11 + 5)  % 40000,
  "61-90j":   (i * 13 + 7)  % 25000,
  ">90j":     (i * 19 + 11) % 60000,
}));

const LIVREURS_SEED = Array.from({ length: 12 }, (_, i) => ({
  name:    `Livreur ${String.fromCharCode(65 + i)}`,
  region:  ["Tunis", "Sfax", "Sousse", "Nabeul"][i % 4],
  ca:      100000 + (i * 37013) % 500000,
  clients: 1 + (i * 7) % 80,
}));

const ATTRITION_SEED = clients.map((c, i) => ({
  ...c,
  attritionScore: parseFloat((((i * 37 + 11) % 100) / 100).toFixed(2)),
}));

function GaugeSimple({ pct, color, label, value }) {
  const r = 55, cx = 75, cy = 70;
  const startA = Math.PI, endA = 0;
  const valA = startA + (endA - startA) * Math.min(pct, 1);
  const arc = (a, rr) => ({ x: cx + rr * Math.cos(a), y: cy + rr * Math.sin(a) });
  const bg   = `M ${arc(startA, r).x} ${arc(startA, r).y} A ${r} ${r} 0 0 1 ${arc(endA, r).x} ${arc(endA, r).y}`;
  const fill = `M ${arc(startA, r).x} ${arc(startA, r).y} A ${r} ${r} 0 ${pct > 0.5 ? 1 : 0} 1 ${arc(valA, r).x} ${arc(valA, r).y}`;
  return (
    <svg width={150} height={85}>
      <path d={bg}   fill="none" stroke="#2a2a2a" strokeWidth={12} strokeLinecap="round" />
      <path d={fill} fill="none" stroke={color}   strokeWidth={12} strokeLinecap="round" />
      <text x={cx} y={cy - 12} textAnchor="middle" fill={color} fontSize={18} fontWeight="bold">{value}</text>
      <text x={cx} y={cy + 4}  textAnchor="middle" fill="#666"  fontSize={10}>{label}</text>
    </svg>
  );
}

function ActeursPage() {
  const { segment, depot } = useFilters();
  const chartH = useChartHeight();
  const kpiLoading    = useSimulatedLoading(500);
  const chartsLoading = useSimulatedLoading(950);


  // Filter clients by segment & depot — stable derivation (no random calls)
  const filteredClients = useMemo(() => {
    return clients.filter((c) => {
      if (segment !== "Tous" && c.segment !== segment) return false;
      if (depot   !== "Tous" && !c.region?.includes(depot.replace("Dépôt ", ""))) return false;
      return true;
    });
  }, [segment, depot]);

  // RFM scatter — derive from stable seed, filtered by client code
  const filteredCodes = useMemo(
    () => new Set(filteredClients.map((c) => c.code)),
    [filteredClients],
  );

  const rfmData = useMemo(
    () => RFM_SEED.filter((d) => filteredCodes.has(d.code)),
    [filteredCodes],
  );

  // Aging — filter by client code
  const agingGRT = useMemo(
    () =>
      AGING_SEED.filter((d) => filteredCodes.has(d.clientCode)).sort(
        (a, b) => b[">90j"] - a[">90j"],
      ),
    [filteredCodes],
  );

  // Livreurs — filter by depot
  const livreurs = useMemo(() => {
    const depotName = depot.replace("Dépôt ", "");
    return (depot === "Tous"
      ? LIVREURS_SEED
      : LIVREURS_SEED.filter((l) => l.region === depotName)
    ).sort((a, b) => b.ca - a.ca);
  }, [depot]);

  // Attrition — filter by same client set
  const atRiskClients = useMemo(
    () =>
      ATTRITION_SEED.filter((c) => filteredCodes.has(c.code) && c.attritionScore > 0.5)
        .sort((a, b) => b.attritionScore - a.attritionScore)
        .slice(0, 8),
    [filteredCodes],
  );

  const attritionPct = filteredClients.length > 0
    ? Math.round((atRiskClients.length / filteredClients.length) * 100)
    : 0;

  const nbActifs = filteredClients.filter((c) => c.actif).length;

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
      <KPICard label="Clients actifs" value={nbActifs.toLocaleString("fr-TN")} subtitle={segment !== "Tous" ? segment : "Tous segments"} icon={Users} />
      <KPICard label="Fournisseurs" value="981" subtitle="3 619 articles couverts" icon={Building2} />
      <KPICard label="Clients à risque attrition" value={`${attritionPct}%`} subtitle="Score local > 0.5" icon={AlertTriangle} />
      <KPICard label="Livreurs actifs" value={String(livreurs.length)} subtitle={depot !== "Tous" ? depot : "Tous dépôts"} icon={Truck} />
    </>
  )}
</div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* RFM scatter */}
        <ChartCard loading={chartsLoading} skeleton="scatter" key={`${segment}-${depot}`} title={`Matrice RFM clients${segment !== "Tous" ? ` — ${segment}` : ""} (KPI-18)`}>
          <ResponsiveContainer width="100%" height={chartH}>
            <ScatterChart margin={{ top: 10, right: 10, bottom: 20, left: 10 }}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis
                dataKey="frequence"
                name="Fréquence"
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                label={{ value: "Fréquence (nb commandes)", position: "insideBottom", offset: -10, fill: "#555", fontSize: 10 }}
              />
              <YAxis
                dataKey="recence"
                name="Récence (j)"
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                label={{ value: "Récence (j)", angle: -90, position: "insideLeft", fill: "#555", fontSize: 10 }}
              />
              <ZAxis dataKey="montant" range={[30, 400]} name="Montant" />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine x={25} stroke="#333" strokeDasharray="4 4" />
              <ReferenceLine y={90} stroke="#333" strokeDasharray="4 4" />
              {Object.entries(rfmSegmentColors).map(([seg, color]) => (
                <Scatter
                  key={seg}
                  name={seg}
                  data={rfmData.filter((d) => d.segment === seg)}
                  fill={color}
                  opacity={0.75}
                />
              ))}
              <Legend wrapperStyle={{ fontSize: 11, color: "#888" }} />
            </ScatterChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Aging GRT */}
        <ChartCard loading={chartsLoading} skeleton="bar" title="Vieillissement créances GRT — par client (KPI-17)">
          <ResponsiveContainer width="100%" height={chartH}>
            <BarChart data={agingGRT}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis dataKey="client" tick={{ fill: "#666", fontSize: 11 }} axisLine={false} />
              <YAxis
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <Tooltip content={<CustomTooltip />} />
              <Legend wrapperStyle={{ fontSize: 11, color: "#888" }} />
              <Bar dataKey="0-30j"  stackId="age" fill="#22c55e" name="0-30j" />
              <Bar dataKey="31-60j" stackId="age" fill="#f97316" name="31-60j" />
              <Bar dataKey="61-90j" stackId="age" fill="#a855f7" name="61-90j" />
              <Bar dataKey=">90j"   stackId="age" fill="#ef4444" name=">90j" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Livreurs */}
        <ChartCard loading={chartsLoading} skeleton="bar" title={`Performance livreurs${depot !== "Tous" ? ` — ${depot}` : ""} (KPI-15)`}>
          <ResponsiveContainer width="100%" height={chartH}>
            <BarChart data={livreurs} layout="vertical">
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" horizontal={false} />
              <XAxis
                type="number"
                tick={{ fill: "#666", fontSize: 11 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <YAxis
                type="category"
                dataKey="name"
                tick={{ fill: "#999", fontSize: 11 }}
                axisLine={false}
                width={70}
              />
              <Tooltip content={<CustomTooltip />} />
              <Bar dataKey="ca" fill="#3b82f6" radius={[0, 4, 4, 0]} name="CA (DT)">
                {livreurs.map((_, i) => (
                  <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        {/* Attrition + HHI */}
        <ChartCard loading={chartsLoading} skeleton="scatter" title="Score attrition clients & Concentration fournisseur (KPI-16/18)">
          <div className="flex gap-4 h-[280px]">
            <div className="flex flex-col items-center pt-2 flex-shrink-0">
              <GaugeSimple
                pct={attritionPct / 100}
                color="#f97316"
                label="Clients à risque"
                value={`${attritionPct}%`}
              />
              <p className="text-[10px] text-text-dim text-center mt-1">seuil &gt; 0.5</p>
              <div className="mt-3 space-y-1 w-full">
                {atRiskClients.slice(0, 5).map((c, i) => (
                  <div key={i} className="flex items-center justify-between text-[10px]">
                    <span className="text-foreground truncate w-20">{c.nom}</span>
                    <div className="flex-1 mx-2 h-1.5 bg-surface-hover rounded-full overflow-hidden">
                      <div
                        className="h-full bg-orange-500 rounded-full"
                        style={{ width: `${c.attritionScore * 100}%` }}
                      />
                    </div>
                    <span className="text-orange-400 font-medium">
                      {(c.attritionScore * 100).toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>

            <div className="flex-1 overflow-auto border-l border-border/40 pl-4">
              <p className="text-[10px] text-text-dim font-semibold uppercase tracking-wider mb-2 mt-2">
                Indice Herfindahl fournisseur (HHI)
              </p>
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-text-dim border-b border-border">
                    <th className="text-left py-1">Article</th>
                    <th className="text-center py-1">HHI</th>
                    <th className="text-left py-1">Fournisseur</th>
                  </tr>
                </thead>
                <tbody>
                  {hhiData.map((row, i) => (
                    <tr key={i} className="border-b border-border/30">
                      <td className="py-1.5 text-foreground text-[10px]">{row.article}</td>
                      <td className="py-1.5 text-center">
                        <span className={`font-semibold ${row.hhi > 0.25 ? "text-red-400" : "text-green-400"}`}>
                          {row.hhi.toFixed(2)}{row.hhi > 0.25 && " ⚠"}
                        </span>
                      </td>
                      <td className="py-1.5 text-text-dim text-[10px]">{row.fournisseur}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <p className="text-[9px] text-text-dim mt-2">Rouge si HHI &gt; 0.25 (dépendance fournisseur)</p>
            </div>
          </div>
        </ChartCard>
      </div>
    </div>
  );
}
