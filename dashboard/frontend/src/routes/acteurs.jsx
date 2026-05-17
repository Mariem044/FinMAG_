import { createFileRoute } from "@tanstack/react-router";
import { KPICard } from "@/components/dashboard/KPICard";
import { useChartHeight, ChartCard } from "@/components/dashboard/ChartCard";
import { CustomTooltip } from "@/components/dashboard/CustomTooltip";
import { Users, Building2, AlertTriangle, Truck } from "lucide-react";
import {
  ScatterChart,
  Scatter,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ZAxis,
  ReferenceLine,
  Cell,
} from "recharts";
import { CHART_COLORS } from "@/lib/dashboardConstants";
import { useFilters } from "@/store/useFilters";
import { useMemo } from "react";
import { api } from "@/lib/api";
import { useApiResource } from "@/hooks/useApiResource";

export const Route = createFileRoute("/acteurs")({
  component: ActeursPage,
});

const rfmSegmentColors = {
  Champion: "#22c55e",
  Fidèle: "#3b82f6",
  "À risque": "#f97316",
  Dormant: "#ef4444",
};

function GaugeSimple({ pct, color, label, value }) {
  const r = 55,
    cx = 75,
    cy = 70;
  const startA = Math.PI,
    endA = 0;
  const valA = startA + (endA - startA) * Math.min(pct, 1);
  const arc = (a, rr) => ({ x: cx + rr * Math.cos(a), y: cy + rr * Math.sin(a) });
  const bg = `M ${arc(startA, r).x} ${arc(startA, r).y} A ${r} ${r} 0 0 1 ${arc(endA, r).x} ${arc(endA, r).y}`;
  const fill = `M ${arc(startA, r).x} ${arc(startA, r).y} A ${r} ${r} 0 ${pct > 0.5 ? 1 : 0} 1 ${arc(valA, r).x} ${arc(valA, r).y}`;
  return (
    <svg width={150} height={85}>
      <path d={bg} fill="none" stroke="#2a2a2a" strokeWidth={12} strokeLinecap="round" />
      <path d={fill} fill="none" stroke={color} strokeWidth={12} strokeLinecap="round" />
      <text x={cx} y={cy - 12} textAnchor="middle" fill={color} fontSize={18} fontWeight="bold">
        {value}
      </text>
      <text x={cx} y={cy + 4} textAnchor="middle" fill="#666" fontSize={10}>
        {label}
      </text>
    </svg>
  );
}

function EmptyState({ message = "Aucune donnée pour ce filtre" }) {
  return (
    <div className="flex items-center justify-center h-full min-h-[160px] text-text-dim text-[13px] italic">
      {message}
    </div>
  );
}

function ActeursPage() {
  const { segment, depot } = useFilters();
  const { data: clients } = useApiResource(api.acteurs.clients, []);
  const { data: rfmRows } = useApiResource(api.acteurs.rfm, []);
  const { data: agingRows } = useApiResource(api.acteurs.aging, []);
  const { data: fournisseurs } = useApiResource(api.acteurs.fournisseurs, []);
  const { data: concentrationFournisseur } = useApiResource(
    api.acteurs.fournisseurConcentration,
    [],
  );
  const chartH = useChartHeight();
  const rfmSeed = useMemo(
    () =>
      rfmRows.map((row) => ({
        ...row,
        segment:
          row.frequence >= 10 && row.recence <= 60
            ? "Champion"
            : row.recence <= 90
              ? "Fidèle"
              : row.montant > 0
                ? "À risque"
                : "Dormant",
      })),
    [rfmRows],
  );
  const attritionSeed = useMemo(
    () =>
      clients.map((c) => ({
        ...c,
        attritionScore: (() => {
          let score = 0;
          const orders = c.nbCommandes || 0;
          const solde = Number(c.soldeImpaye || 0);
          const dormant = !c.actif;
          // Only penalize zero orders if also dormant (avoid false positives for new clients)
          if (orders === 0 && dormant) score += 0.35;
          else if (orders === 0) score += 0.15;
          else if (orders < 3) score += 0.10;
          // Overdue balance — normalized to realistic TND ranges
          if (solde > 50000) score += 0.35;
          else if (solde > 15000) score += 0.20;
          else if (solde > 3000) score += 0.10;
          // Dormant without any balance = moderate signal
          if (dormant && solde === 0) score += 0.15;
          else if (dormant) score += 0.10;
          return Math.min(parseFloat(score.toFixed(2)), 1.0);
        })(),
      })),
    [clients],
  );

  const filteredClients = useMemo(() => {
    return clients.filter((c) => {
      if (segment !== "Tous" && c.segment !== segment) return false;

      if (depot !== "Tous") {
        const regionFragment = depot.replace("Dépôt ", "");
        if (!c.region?.toLowerCase().includes(regionFragment.toLowerCase())) return false;
      }
      return true;
    });
  }, [clients, segment, depot]);

  const filteredCodes = useMemo(
    () => new Set(filteredClients.map((c) => c.code)),
    [filteredClients],
  );

  const rfmData = useMemo(
    () => rfmSeed.filter((d) => filteredCodes.has(d.code)),
    [filteredCodes, rfmSeed],
  );

  const agingGRT = useMemo(
    () =>
      agingRows
        .filter((d) => filteredCodes.has(d.clientCode))
        .sort((a, b) => b[">90j"] - a[">90j"])
        .slice(0, 8),
    [filteredCodes, agingRows],
  );

  const livreurs = useMemo(() => [], [depot]);

  const atRiskClients = useMemo(
    () =>
      attritionSeed
        .filter((c) => filteredCodes.has(c.code) && c.attritionScore > 0.5)
        .sort((a, b) => b.attritionScore - a.attritionScore)
        .slice(0, 8),
    [filteredCodes, attritionSeed],
  );

  const nbActifs = filteredClients.filter((c) => c.actif).length;

  const attritionPct =
    filteredClients.length > 0
      ? Math.round((atRiskClients.length / filteredClients.length) * 100)
      : 0;

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <KPICard
          label="Clients actifs"
          value={nbActifs.toLocaleString("fr-TN")}
          subtitle={segment !== "Tous" ? segment : "Tous segments"}
          icon={Users}
        />
        <KPICard
          label="Fournisseurs"
          value={fournisseurs.length.toLocaleString("fr-TN")}
          subtitle={`${fournisseurs.reduce((s, f) => s + (f.nbArticles || 0), 0).toLocaleString("fr-TN")} articles couverts`}
          icon={Building2}
        />
        <KPICard
          label="Clients à risque attrition"
          value={`${attritionPct}%`}
          subtitle="Score > 0.5 (RF model)"
          icon={AlertTriangle}
        />
        <KPICard
          label="Livreurs actifs"
          value={String(livreurs.length)}
          subtitle="Non disponible dans le DW"
          icon={Truck}
        />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <ChartCard
          key={`rfm-${segment}-${depot}`}
          title={`Matrice RFM clients${segment !== "Tous" ? ` — ${segment}` : ""}`}
        >
          {rfmData.length === 0 ? (
            <EmptyState />
          ) : (
            <ResponsiveContainer width="100%" height={chartH}>
              <ScatterChart margin={{ top: 10, right: 10, bottom: 20, left: 10 }}>
                <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
                <XAxis
                  dataKey="frequence"
                  name="Fréquence"
                  tick={{ fill: "#666", fontSize: 11 }}
                  axisLine={false}
                  label={{
                    value: "Fréquence (nb commandes)",
                    position: "insideBottom",
                    offset: -10,
                    fill: "#555",
                    fontSize: 10,
                  }}
                />
                <YAxis
                  dataKey="recence"
                  name="Récence (j)"
                  tick={{ fill: "#666", fontSize: 11 }}
                  axisLine={false}
                  label={{
                    value: "Récence (j)",
                    angle: -90,
                    position: "insideLeft",
                    fill: "#555",
                    fontSize: 10,
                  }}
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
          )}
        </ChartCard>

        <ChartCard
          key={`aging-${segment}-${depot}`}
          title="Vieillissement créances GRT — par client"
        >
          {agingGRT.length === 0 ? (
            <EmptyState />
          ) : (
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
                <Bar dataKey="0-30j" stackId="age" fill="#22c55e" name="0-30j" />
                <Bar dataKey="31-60j" stackId="age" fill="#f97316" name="31-60j" />
                <Bar dataKey="61-90j" stackId="age" fill="#a855f7" name="61-90j" />
                <Bar
                  dataKey=">90j"
                  stackId="age"
                  fill="#ef4444"
                  name=">90j"
                  radius={[4, 4, 0, 0]}
                />
              </BarChart>
            </ResponsiveContainer>
          )}
        </ChartCard>

        <ChartCard
          key={`livreurs-${depot}`}
          title={`Performance livreurs${depot !== "Tous" ? ` — ${depot}` : ""}`}
        >
          {livreurs.length === 0 ? (
            <EmptyState />
          ) : (
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
          )}
        </ChartCard>

        <ChartCard title="Score attrition clients & Concentration fournisseur">
          <div className="flex gap-4 h-[280px]">
            <div className="flex flex-col items-center pt-2 flex-shrink-0">
              <GaugeSimple
                pct={attritionPct / 100}
                color="#f97316"
                label="Clients à risque"
                value={`${attritionPct}%`}
              />
              <p className="text-[10px] text-text-dim text-center mt-1">seuil &gt; 0.5</p>

              {atRiskClients.length === 0 ? (
                <p className="text-[11px] text-text-dim mt-3 text-center italic">
                  Aucun client à risque
                </p>
              ) : (
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
              )}
            </div>

            <div className="flex-1 overflow-auto border-l border-border/40 pl-4">
              <p className="text-[10px] text-text-dim font-semibold uppercase tracking-wider mb-2 mt-2">
                Concentration fournisseur
              </p>
              <table className="w-full text-[11px]">
                <thead>
                  <tr className="text-text-dim border-b border-border">
                    <th className="text-left py-1">Fournisseur</th>
                    <th className="text-center py-1">Articles</th>
                    <th className="text-left py-1">Valeur ref.</th>
                  </tr>
                </thead>
                <tbody>
                  {concentrationFournisseur.map((row, i) => (
                    <tr key={i} className="border-b border-border/30">
                      <td className="py-1.5 text-foreground text-[10px]">{row.fournisseur}</td>
                      <td className="py-1.5 text-center">
                        <span className="font-semibold text-foreground">{row.nbArticles}</span>
                      </td>
                      <td className="py-1.5 text-text-dim text-[10px]">
                        {row.montantAchat > 0 && isFinite(row.montantAchat)
                          ? Math.round(Number(row.montantAchat)).toLocaleString("fr-TN")
                          : "—"}
                      </td>
                    </tr>
                  ))}
                  {concentrationFournisseur.length === 0 && (
                    <tr>
                      <td colSpan={3} className="py-8 text-center text-text-dim">
                        Aucune donnée fournisseur disponible dans le DW
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
              <p className="text-[9px] text-text-dim mt-2">
                Données réelles DIM_FOURNISSEUR / DIM_ARTICLE
              </p>
            </div>
          </div>
        </ChartCard>
      </div>
    </div>
  );
}
