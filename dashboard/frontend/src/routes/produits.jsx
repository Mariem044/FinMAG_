import { createFileRoute } from "@tanstack/react-router";
import { useChartHeight, ChartCard, KPICardSkeleton } from "@/components/dashboard/ChartCard";
import { KPICard } from "@/components/dashboard/KPICard";
import { CustomTooltip } from "@/components/dashboard/CustomTooltip";
import { Boxes, AlertTriangle, Clock, Bell, Search, Brain, Cpu, ShieldCheck, Sparkles, TrendingUp } from "lucide-react";
import {
  ScatterChart,
  Scatter,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  ZAxis,
  ReferenceLine,
} from "recharts";
import { FAMILLES, CHART_COLORS, formatTND } from "@/lib/dashboardConstants";
import { useFilters } from "@/store/useFilters";
import { useMemo, useState } from "react";
import { api } from "@/lib/api";
import { useApiResource } from "@/hooks/useApiResource";

export const Route = createFileRoute("/produits")({
  component: ProduitsPage,
});

function rotationColor(r) {
  if (r < 0.33) return "#ef4444";
  if (r < 0.66) return "#f97316";
  return "#22c55e";
}

function priorityBadge(p) {
  const map = {
    CRITIQUE: "bg-red-500/20 text-red-400 border border-red-500/30",
    URGENT: "bg-orange-500/20 text-orange-400 border border-orange-500/30",
    ATTENTION: "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30",
  };
  return map[p] || "bg-emerald-500/10 text-emerald-400 border border-emerald-500/20";
}

function GaugeChart({ value, target, label, maxVal = 100 }) {
  const pct = Math.min(value / maxVal, 1);
  const r = 70,
    cx = 100,
    cy = 90;
  const startA = Math.PI,
    endA = 0;
  const valA = startA + (endA - startA) * pct;
  const arcX = (a, rr) => cx + rr * Math.cos(a);
  const arcY = (a, rr) => cy + rr * Math.sin(a);
  const bgPath = `M ${arcX(startA, r)} ${arcY(startA, r)} A ${r} ${r} 0 0 1 ${arcX(endA, r)} ${arcY(endA, r)}`;
  const valPath = `M ${arcX(startA, r)} ${arcY(startA, r)} A ${r} ${r} 0 ${pct > 0.5 ? 1 : 0} 1 ${arcX(valA, r)} ${arcY(valA, r)}`;
  
  // Decide color depending on gauge type
  const isR2 = label.includes("R²");
  const color = isR2 
    ? (value >= target ? "#10b981" : value >= 60 ? "#f97316" : "#ef4444")
    : (value <= target ? "#10b981" : value <= target * 2 ? "#f97316" : "#ef4444");

  return (
    <div className="flex flex-col items-center">
      <svg width={200} height={105}>
        <path d={bgPath} fill="none" stroke="#2a2a2a" strokeWidth={11} strokeLinecap="round" />
        <path d={valPath} fill="none" stroke={color} strokeWidth={11} strokeLinecap="round" />
        <line
          x1={cx}
          y1={cy}
          x2={arcX(valA, r - 15)}
          y2={arcY(valA, r - 15)}
          stroke={color}
          strokeWidth={1.5}
          strokeLinecap="round"
        />
        <circle cx={cx} cy={cy} r={3} fill={color} />
        <text x={cx} y={cy - 14} textAnchor="middle" fill={color} fontSize={18} fontWeight="bold">
          {value}%
        </text>
        <text x={cx} y={cy - 1} textAnchor="middle" fill="#666" fontSize={8.5}>
          {isR2 ? `cible > ${target}%` : `limite < ${target}%`}
        </text>
        <text x={cx} y={100} textAnchor="middle" fill="#999" fontSize={9.5} fontWeight="semibold" className="tracking-wide">
          {label}
        </text>
      </svg>
    </div>
  );
}

function ProduitsPage() {
  const { famille, statutArticle, horizonPrev, depot, getActiveMonthIndexes } = useFilters();
  const { data: articles, loading: articlesLoading } = useApiResource(api.produits.articles, []);

  const avgR2 = useMemo(() => {
    const validScores = articles.map(a => a.r2Score).filter(s => s !== undefined && s !== null);
    if (validScores.length === 0) return 76; // default
    return Math.round(validScores.reduce((s, v) => s + v, 0) / validScores.length * 100);
  }, [articles]);

  const [searchQuery, setSearchQuery] = useState("");

  const activeIdx = getActiveMonthIndexes();
  const chartH = useChartHeight();
  const kpiLoading = articlesLoading;
  const chartsLoading = articlesLoading;

  const filteredArticles = useMemo(() => {
    return articles.filter((a) => {
      if (famille !== "Toutes" && a.famille !== famille) return false;
      if (statutArticle === "En sommeil" && a.qteVendue > 100) return false;
      if (statutArticle === "Actifs uniquement" && a.qteVendue === 0) return false;

      if (searchQuery) {
        const q = searchQuery.toLowerCase();
        const matchesDesignation = a.designation && a.designation.toLowerCase().includes(q);
        const matchesArticle = (a.ref || a.code || a.article || "").toLowerCase().includes(q);
        if (!matchesDesignation && !matchesArticle) return false;
      }
      return true;
    });
  }, [articles, famille, statutArticle, searchQuery]);

  const dsiScatter = useMemo(() => {
    return filteredArticles.slice(0, 40).map((a) => ({
      dsi: Math.round(a.dsi || 0),
      ca: a.ca,
      stockVal: Math.round((a.stock || 0) * (a.prixMoyen || 0)),
      name: a.designation,
    }));
  }, [filteredArticles]);

  const valeurStock = filteredArticles.reduce((s, a) => s + (a.stock || 0) * (a.prixMoyen || 0), 0);
  const nbRuptures = filteredArticles.filter(a => (a.stock || 0) <= 0).length;
  const dsiMoyen = Math.round(
    dsiScatter.reduce((s, d) => s + d.dsi, 0) / Math.max(dsiScatter.length, 1),
  );
  const nbArticles = filteredArticles.length;
  const txRupture = parseFloat(
    ((nbRuptures / Math.max(filteredArticles.length, 1)) * 100).toFixed(1),
  );

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
              label="Valeur stock"
              value={`${(valeurStock / 1000000).toFixed(1)} MDT`}
              subtitle={famille !== "Toutes" ? famille : "Tous dépôts"}
              icon={Boxes}
            />
            <KPICard
              label="Articles en rupture"
              value={String(nbRuptures)}
              subtitle={`sur ${filteredArticles.length} actifs (${txRupture}%)`}
              icon={AlertTriangle}
            />
            <KPICard
              label="DSI moyen (rotation)"
              value={`${dsiMoyen}j`}
              subtitle="Days Sales of Inventory"
              icon={Clock}
            />
            <KPICard
              label="Nombre d'articles"
              value={String(nbArticles)}
              subtitle="Sélection filtrée"
              icon={Boxes}
            />
          </>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Catalogue Produits (Sage) Table */}
        <ChartCard
          loading={chartsLoading}
          skeleton="table"
          title="Catalogue des Produits & Niveaux de Stock"
        >
          <div className="flex flex-col md:flex-row gap-3 mb-4 items-center justify-between relative z-20">
            {/* Search Input */}
            <div className="relative w-full md:w-60">
              <Search className="absolute left-3 top-2.5 h-3.5 w-3.5 text-text-dim" />
              <input
                type="text"
                placeholder="Rechercher SKU, Désignation..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-4 py-1.5 w-full text-[11px] bg-surface/40 hover:bg-surface/60 focus:bg-surface-hover/50 border border-border/40 focus:border-primary/50 focus:ring-1 focus:ring-primary/20 rounded-lg focus:outline-none transition-all duration-300 backdrop-blur-md text-foreground placeholder:text-text-dim"
              />
            </div>
            <div className="text-[10px] text-text-dim">
              Affichage de {filteredArticles.slice(0, 100).length} sur {filteredArticles.length} articles
            </div>
          </div>

          <div className="overflow-auto max-h-[280px]">
            <table className="w-full text-[11px]">
              <thead className="sticky top-0 bg-background">
                <tr className="text-text-dim border-b border-border">
                  <th className="text-left py-1.5 px-2">Référence / Désignation</th>
                  <th className="text-left py-1.5 px-2">Famille</th>
                  <th className="text-right py-1.5 px-2">Stock dispo</th>
                  <th className="text-right py-1.5 px-2">Prix Moyen</th>
                  <th className="text-right py-1.5 px-2">CA Généré</th>
                  <th className="text-right py-1.5 px-2">DSI (Rotation)</th>
                </tr>
              </thead>
              <tbody>
                {filteredArticles.slice(0, 100).map((row, i) => (
                  <tr key={i} className="border-b border-border/30 hover:bg-surface-hover/30 transition-all duration-200">
                    <td className="py-2 px-2">
                      <div className="font-semibold text-foreground truncate max-w-[155px]">{row.designation || 'Article sans nom'}</div>
                      <div className="text-text-dim text-[9.5px] font-mono">{row.ref || row.code || `ART-${row.id}`}</div>
                    </td>
                    <td className="py-2 px-2 text-left text-text-dim truncate max-w-[100px]">
                      {row.famille || '-'}
                    </td>
                    <td className="py-2 px-2 text-right font-bold">
                      {Math.round(row.stock || 0)}
                    </td>
                    <td className="py-2 px-2 text-right text-text-dim font-mono">
                      {formatTND(row.prixMoyen || 0)}
                    </td>
                    <td className="py-2 px-2 text-right font-mono font-bold text-cyan-400">
                      {formatTND(row.ca || 0)}
                    </td>
                    <td className="py-2 px-2 text-right">
                      <span className={`px-1.5 py-0.5 rounded text-[9.5px] font-semibold ${
                        (row.dsi || 0) > 90 ? 'bg-red-500/10 text-red-400' :
                        (row.dsi || 0) > 30 ? 'bg-yellow-500/10 text-yellow-400' :
                        'bg-green-500/10 text-green-400'
                      }`}>
                        {Math.round(row.dsi || 0)}j
                      </span>
                    </td>
                  </tr>
                ))}
                {filteredArticles.length === 0 && (
                  <tr>
                    <td colSpan={6} className="py-12 text-center text-text-dim">
                      Aucun article ne correspond aux critères
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </ChartCard>

        {/* Dynamic Rotation Scatter plot */}
        <ChartCard
          loading={chartsLoading}
          skeleton="scatter"
          title="Rotation Stocks — DSI vs CA par article"
        >
          <ResponsiveContainer width="100%" height={chartH}>
            <ScatterChart margin={{ top: 10, right: 10, bottom: 20, left: 10 }}>
              <CartesianGrid stroke="#2a2a2a" strokeDasharray="3 3" />
              <XAxis
                dataKey="dsi"
                name="DSI (j)"
                tick={{ fill: "#666", fontSize: 10 }}
                axisLine={false}
                label={{
                  value: "DSI (jours)",
                  position: "insideBottom",
                  offset: -10,
                  fill: "#555",
                  fontSize: 10,
                }}
              />
              <YAxis
                dataKey="ca"
                name="CA"
                tick={{ fill: "#666", fontSize: 10 }}
                axisLine={false}
                tickFormatter={(v) => `${(v / 1000).toFixed(0)}K`}
              />
              <ZAxis dataKey="stockVal" range={[40, 400]} name="Valeur stock" />
              <Tooltip content={<CustomTooltip />} />
              <ReferenceLine
                x={dsiMoyen}
                stroke="#444"
                strokeDasharray="4 4"
                label={{ value: "DSI moy.", fill: "#555", fontSize: 9, position: "top" }}
              />
              <Scatter
                data={dsiScatter}
                fill="#3b82f6"
                opacity={0.7}
                shape={(props) => {
                  const { cx, cy, payload } = props;
                  const avgCa =
                    filteredArticles.reduce((s, a) => s + a.ca, 0) /
                    Math.max(filteredArticles.length, 1);
                  const isStar = payload.dsi < dsiMoyen && payload.ca > avgCa;
                  const isSlow = payload.dsi >= dsiMoyen && payload.ca <= avgCa;
                  return (
                    <circle
                      cx={cx}
                      cy={cy}
                      r={5}
                      fill={isStar ? "#10b981" : isSlow ? "#ef4444" : "#3b82f6"}
                      opacity={0.75}
                    />
                  );
                }}
              />
            </ScatterChart>
          </ResponsiveContainer>
          <div className="flex gap-4 text-[9.5px] text-text-dim mt-1 justify-end">
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-green-500 inline-block" /> Star / Fast
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-blue-500 inline-block" /> Normal
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2 h-2 rounded-full bg-red-500 inline-block" /> Sleeping / Slow
            </span>
          </div>
        </ChartCard>
      </div>


    </div>
  );
}

