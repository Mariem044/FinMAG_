import { useState, useRef, useEffect, useCallback } from "react";
import { useNavigate } from "@tanstack/react-router";
import {
  Search, X, ArrowRight,
  LayoutDashboard, TrendingUp, Wallet, Boxes, Users,
  Receipt, Banknote, Landmark, Settings, HelpCircle,
  User, Package, FileText, Truck,
} from "lucide-react";
import {
  clients, articles, ecritures, fournisseurs, representants,
} from "@/data/mockData";

// ─── Static pages + KPIs ─────────────────────────────────────────────────────
const PAGES = [
  { label: "Tableau de Bord",               description: "Vue d'ensemble générale",              to: "/",           icon: LayoutDashboard, keywords: ["dashboard","accueil","overview","tableau"] },
  { label: "CA & Performance Commerciale",   description: "Chiffre d'affaires, ventes, familles", to: "/ventes",     icon: TrendingUp,      keywords: ["ventes","ca","chiffre affaires","commercial","familles"] },
  { label: "Trésorerie & Flux de Paiement",  description: "Encaissements, impayés, recouvrement", to: "/tresorerie", icon: Wallet,          keywords: ["tresorerie","paiement","flux","encaissement","impaye"] },
  { label: "Stocks & Approvisionnement",     description: "Inventaire, ruptures, alertes stock",  to: "/produits",   icon: Boxes,           keywords: ["stock","produit","inventaire","rupture","approvisionnement"] },
  { label: "Analyse Acteurs & Segmentation", description: "Clients, fournisseurs, livreurs, RFM", to: "/acteurs",    icon: Users,           keywords: ["client","fournisseur","acteur","segment","rfm","livreur"] },
  { label: "Fiscalité & Comptabilité",       description: "Écritures, TVA, anomalies",            to: "/fiscalite",  icon: Receipt,         keywords: ["fiscalite","comptabilite","ecriture","tva","journal"] },
  { label: "Gestion de Caisse",              description: "Soldes, flux journaliers, prévisions",  to: "/caisse",     icon: Banknote,        keywords: ["caisse","especes","solde","flux"] },
  { label: "Rapprochement Bancaire",         description: "Bordereaux, agios, remises en banque",  to: "/banque",     icon: Landmark,        keywords: ["banque","rapprochement","bordereau","agio","remise"] },
  { label: "Paramètres",                     description: "Langue et devise",                       to: "/parametres", icon: Settings,        keywords: ["parametres","settings","langue","devise"] },
  { label: "Centre d'Aide",                  description: "FAQ, support, contact",                 to: "/aide",       icon: HelpCircle,      keywords: ["aide","help","faq","support"] },
];

const KPIS = [
  { label: "Taux de recouvrement",        description: "KPI-07 — Encaissements clients",     to: "/tresorerie", icon: Wallet,   keywords: ["recouvrement","taux","encaissement"] },
  { label: "Score d'attrition clients",   description: "KPI-24 — Score de risque client",     to: "/acteurs",    icon: Users,    keywords: ["attrition","score","client","risque"] },
  { label: "Détection anomalies",         description: "KPI-28 — Scores d'anomalie",          to: "/fiscalite",  icon: Receipt,  keywords: ["anomalie","detection","isolation"] },
  { label: "Prévision trésorerie",        description: "KPI-11 — Projection 30/60/90j",       to: "/tresorerie", icon: Wallet,   keywords: ["prevision","projection","tresorerie"] },
  { label: "DSI — Rotation stocks",       description: "KPI-15 — Days Sales of Inventory",   to: "/produits",   icon: Boxes,    keywords: ["dsi","rotation","stock","inventory"] },
  { label: "Matrice RFM",                 description: "KPI-22 — Segmentation clients",      to: "/acteurs",    icon: Users,    keywords: ["rfm","recence","frequence","montant"] },
  { label: "Solde de caisse",             description: "KPI-29 — Toutes caisses",             to: "/caisse",     icon: Banknote, keywords: ["solde","caisse","especes"] },
  { label: "Taux rapprochement bancaire", description: "KPI-34 — Réconciliation",             to: "/banque",     icon: Landmark, keywords: ["rapprochement","bancaire","taux"] },
];

const CATEGORY_META = {
  pages:         { label: "Pages",         color: "text-blue-400",   bg: "bg-blue-500/15",   max: 3 },
  kpis:          { label: "KPIs",          color: "text-violet-400", bg: "bg-violet-500/15", max: 3 },
  clients:       { label: "Clients",       color: "text-green-400",  bg: "bg-green-500/15",  max: 3 },
  articles:      { label: "Articles",      color: "text-orange-400", bg: "bg-orange-500/15", max: 3 },
  ecritures:     { label: "Écritures",     color: "text-pink-400",   bg: "bg-pink-500/15",   max: 3 },
  fournisseurs:  { label: "Fournisseurs",  color: "text-yellow-400", bg: "bg-yellow-500/15", max: 2 },
  representants: { label: "Représentants", color: "text-teal-400",   bg: "bg-teal-500/15",   max: 2 },
};

function normalize(str) {
  return (str || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}

function matches(fields, q) {
  const nq = normalize(q);
  return fields.some((f) => normalize(f).includes(nq));
}

function Highlight({ text, query }) {
  if (!query) return <>{text}</>;
  const nText  = normalize(text);
  const nQuery = normalize(query);
  const idx    = nText.indexOf(nQuery);
  if (idx === -1) return <>{text}</>;
  return (
    <>
      {text.slice(0, idx)}
      <mark className="bg-primary/25 text-primary rounded px-0.5 not-italic">
        {text.slice(idx, idx + query.length)}
      </mark>
      {text.slice(idx + query.length)}
    </>
  );
}

function runSearch(q) {
  if (!q.trim()) return {};
  const results = {};

  const pages = PAGES.filter((p) => matches([p.label, p.description, ...p.keywords], q)).slice(0, CATEGORY_META.pages.max);
  if (pages.length) results.pages = pages.map((p) => ({ ...p, type: "pages", subtitle: p.description }));

  const kpis = KPIS.filter((k) => matches([k.label, k.description, ...k.keywords], q)).slice(0, CATEGORY_META.kpis.max);
  if (kpis.length) results.kpis = kpis.map((k) => ({ ...k, type: "kpis", subtitle: k.description }));

  const foundClients = clients.filter((c) => matches([c.nom, c.code, c.region, c.segment], q)).slice(0, CATEGORY_META.clients.max);
  if (foundClients.length) results.clients = foundClients.map((c) => ({ label: c.nom, subtitle: `${c.code} · ${c.region} · ${c.segment}`, to: "/acteurs", icon: User, type: "clients" }));

  const foundArticles = articles.filter((a) => matches([a.designation, a.code, a.famille], q)).slice(0, CATEGORY_META.articles.max);
  if (foundArticles.length) results.articles = foundArticles.map((a) => ({ label: a.designation, subtitle: `${a.code} · ${a.famille}`, to: "/produits", icon: Package, type: "articles" }));

  const foundEcritures = ecritures.filter((e) => matches([e.libelle, e.journal, e.compte, e.numPiece], q)).slice(0, CATEGORY_META.ecritures.max);
  if (foundEcritures.length) results.ecritures = foundEcritures.map((e) => ({ label: e.libelle, subtitle: `${e.numPiece} · ${e.journal} · ${e.date}`, to: "/fiscalite", icon: FileText, type: "ecritures" }));

  const foundFournisseurs = fournisseurs.filter((f) => matches([f.nom, f.famille], q)).slice(0, CATEGORY_META.fournisseurs.max);
  if (foundFournisseurs.length) results.fournisseurs = foundFournisseurs.map((f) => ({ label: f.nom, subtitle: `${f.famille} · ${f.nbCommandes} commandes`, to: "/acteurs", icon: Truck, type: "fournisseurs" }));

  const foundReps = representants.filter((r) => matches([r.nom, r.region], q)).slice(0, CATEGORY_META.representants.max);
  if (foundReps.length) results.representants = foundReps.map((r) => ({ label: r.nom, subtitle: `${r.region} · ${r.nbClients} clients`, to: "/acteurs", icon: Users, type: "representants" }));

  return results;
}

export function SearchBar() {
  const [query, setQuery]       = useState("");
  const [open, setOpen]         = useState(false);
  const [activeKey, setActiveKey] = useState(null);
  const inputRef    = useRef(null);
  const dropdownRef = useRef(null);
  const navigate    = useNavigate();

  const grouped      = query.trim().length >= 1 ? runSearch(query) : {};
  const categories   = Object.keys(grouped);
  const flat         = categories.flatMap((cat) => grouped[cat].map((item, i) => ({ cat, i, item })));
  const activeFlat   = flat.findIndex((f) => `${f.cat}:${f.i}` === activeKey);
  const hasResults   = flat.length > 0;
  const showDropdown = open && query.trim().length >= 1;

  const go = useCallback((to) => {
    navigate({ to });
    setQuery("");
    setOpen(false);
    inputRef.current?.blur();
  }, [navigate]);

  useEffect(() => {
    setActiveKey(flat[0] ? `${flat[0].cat}:${flat[0].i}` : null);
  }, [query]);

  useEffect(() => {
    function handleClick(e) {
      if (!dropdownRef.current?.contains(e.target) && !inputRef.current?.contains(e.target)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  useEffect(() => {
    function handleKey(e) {
      if ((e.ctrlKey || e.metaKey) && e.key === "k") { e.preventDefault(); inputRef.current?.focus(); setOpen(true); }
      if (e.key === "Escape") { setOpen(false); setQuery(""); inputRef.current?.blur(); }
    }
    document.addEventListener("keydown", handleKey);
    return () => document.removeEventListener("keydown", handleKey);
  }, []);

  function handleKeyDown(e) {
    if (!open || flat.length === 0) return;
    if (e.key === "ArrowDown") { e.preventDefault(); const next = Math.min(activeFlat + 1, flat.length - 1); setActiveKey(`${flat[next].cat}:${flat[next].i}`); }
    if (e.key === "ArrowUp")   { e.preventDefault(); const prev = Math.max(activeFlat - 1, 0); setActiveKey(`${flat[prev].cat}:${flat[prev].i}`); }
    if (e.key === "Enter")     { e.preventDefault(); const active = flat[activeFlat]; if (active) go(active.item.to); }
  }

  return (
    <div className="relative flex-1 max-w-xl mx-3">
      {/* Input */}
      <div className={`w-full flex items-center gap-2 px-3 py-2 rounded-xl border transition-all duration-200
        ${showDropdown && hasResults
          ? "border-primary/60 shadow-md shadow-primary/20 bg-surface rounded-b-none"
          : "border-primary/25 bg-gradient-to-r from-surface/95 via-surface/85 to-surface/70 shadow-sm shadow-primary/10"
        }`}
      >
        <Search size={14} className="text-primary/80 flex-shrink-0" />
        <input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => { setQuery(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          onKeyDown={handleKeyDown}
          placeholder="Rechercher pages, KPIs, clients, articles… (Ctrl+K)"
          className="w-full bg-transparent text-[12px] text-foreground placeholder:text-text-dim outline-none"
          autoComplete="off"
          spellCheck={false}
        />
        {query && (
          <button onClick={() => { setQuery(""); inputRef.current?.focus(); }} className="text-text-dim hover:text-foreground transition-colors flex-shrink-0">
            <X size={13} />
          </button>
        )}
        <span className="hidden lg:flex items-center gap-0.5 flex-shrink-0">
          <kbd className="text-[9px] text-text-dim bg-surface-hover border border-border rounded px-1 py-0.5 font-mono">Ctrl</kbd>
          <kbd className="text-[9px] text-text-dim bg-surface-hover border border-border rounded px-1 py-0.5 font-mono">K</kbd>
        </span>
      </div>

      {/* Dropdown */}
      {showDropdown && (
        <div ref={dropdownRef} className="absolute left-0 right-0 top-full z-50 rounded-b-xl border border-t-0 border-border bg-popover shadow-2xl shadow-black/30 overflow-hidden">
          {hasResults ? (
            <>
              <div className="max-h-[420px] overflow-y-auto">
                {categories.map((cat) => {
                  const meta  = CATEGORY_META[cat];
                  const items = grouped[cat];
                  return (
                    <div key={cat}>
                      {/* Category header */}
                      <div className="flex items-center gap-2 px-3 pt-3 pb-1.5">
                        <span className={`text-[10px] font-bold uppercase tracking-widest ${meta.color}`}>{meta.label}</span>
                        <span className={`text-[9px] font-semibold px-1.5 py-0.5 rounded-full ${meta.bg} ${meta.color}`}>{items.length}</span>
                        <div className="flex-1 h-px bg-border/40" />
                      </div>
                      {/* Items */}
                      {items.map((item, i) => {
                        const Icon     = item.icon;
                        const key      = `${cat}:${i}`;
                        const isActive = activeKey === key;
                        return (
                          <button
                            key={i}
                            onMouseEnter={() => setActiveKey(key)}
                            onClick={() => go(item.to)}
                            className={`w-full flex items-center gap-3 px-3 py-2.5 text-left transition-colors duration-75 ${isActive ? "bg-primary/10" : "hover:bg-surface-hover/50"}`}
                          >
                            <div className={`w-7 h-7 rounded-lg flex items-center justify-center flex-shrink-0 transition-colors ${isActive ? meta.bg : "bg-surface-hover"}`}>
                              <Icon size={13} className={isActive ? meta.color : "text-text-muted"} />
                            </div>
                            <div className="flex-1 min-w-0">
                              <p className="text-[12px] font-medium text-foreground truncate">
                                <Highlight text={item.label} query={query} />
                              </p>
                              <p className="text-[10px] text-text-dim truncate">
                                <Highlight text={item.subtitle} query={query} />
                              </p>
                            </div>
                            {isActive && <ArrowRight size={13} className={`flex-shrink-0 ${meta.color}`} />}
                          </button>
                        );
                      })}
                    </div>
                  );
                })}
              </div>
              {/* Footer */}
              <div className="border-t border-border/60 px-3 py-2 flex items-center justify-between bg-surface/50">
                <div className="flex items-center gap-3 text-[10px] text-text-dim">
                  <span className="flex items-center gap-1"><kbd className="bg-surface-hover border border-border rounded px-1 font-mono">↑↓</kbd> naviguer</span>
                  <span className="flex items-center gap-1"><kbd className="bg-surface-hover border border-border rounded px-1 font-mono">↵</kbd> ouvrir</span>
                  <span className="flex items-center gap-1"><kbd className="bg-surface-hover border border-border rounded px-1 font-mono">Esc</kbd> fermer</span>
                </div>
                <span className="text-[10px] text-text-dim">{flat.length} résultat{flat.length > 1 ? "s" : ""}</span>
              </div>
            </>
          ) : (
            <div className="px-4 py-8 text-center">
              <Search size={22} className="text-text-dim mx-auto mb-2.5" />
              <p className="text-[13px] font-medium text-foreground">Aucun résultat pour « {query} »</p>
              <p className="text-[11px] text-text-dim mt-1">Essayez : un nom de client, article, journal, page…</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
