export const MONTHS = [
  "Jan",
  "Fév",
  "Mar",
  "Avr",
  "Mai",
  "Jun",
  "Jul",
  "Aoû",
  "Sep",
  "Oct",
  "Nov",
  "Déc",
];
export const REGIONS = [
  "Tunis",
  "Sfax",
  "Sousse",
  "Nabeul",
  "Bizerte",
  "Gabès",
  "Kairouan",
  "Monastir",
];
export const FAMILLES = [
  "Biscuits",
  "Boissons",
  "Conserves",
  "Produits Laitiers",
  "Confiserie",
  "Épicerie",
  "Huiles",
  "Pâtes",
];
export const QUARTERS = ["Q1", "Q2", "Q3", "Q4"];
export const CHART_COLORS = [
  "#3b82f6",
  "#6366f1",
  "#8b5cf6",
  "#a855f7",
  "#ec4899",
  "#f97316",
  "#22c55e",
  "#14b8a6",
];
export const caByMonth = MONTHS.map((m, i) => ({
  month: m,
  ca: Math.round(800000 + Math.random() * 600000),
  objectif: Math.round(900000 + Math.random() * 300000),
  caN1: Math.round(700000 + Math.random() * 500000),
}));
export const topFamilles = FAMILLES.map((f) => ({
  name: f,
  ca: Math.round(500000 + Math.random() * 2000000),
}))
  .sort((a, b) => b.ca - a.ca)
  .slice(0, 5);
export const caByRegion = REGIONS.map((r) => ({
  name: r,
  ca: Math.round(300000 + Math.random() * 1500000),
  clients: Math.round(20 + Math.random() * 80),
  commandes: Math.round(100 + Math.random() * 500),
}));
export const ventesDetail = Array.from({ length: 50 }, (_, i) => ({
  id: `VNT-${2024}${String(i + 1).padStart(4, "0")}`,
  date: `2024-${String(Math.ceil(Math.random() * 12)).padStart(2, "0")}-${String(Math.ceil(Math.random() * 28)).padStart(2, "0")}`,
  client: `Client ${Math.ceil(Math.random() * 30)}`,
  clientCode: `CL${String(Math.ceil(Math.random() * 30)).padStart(3, "0")}`,
  famille: FAMILLES[Math.floor(Math.random() * FAMILLES.length)],
  article: `Article ${Math.ceil(Math.random() * 100)}`,
  quantite: Math.ceil(Math.random() * 200),
  prixUnitaire: Math.round(5 + Math.random() * 50),
  montantHT: 0,
  montantTTC: 0,
  region: REGIONS[Math.floor(Math.random() * REGIONS.length)],
  representant: `Rep ${Math.ceil(Math.random() * 10)}`,
  lignes: Array.from({ length: Math.ceil(Math.random() * 4) }, (_, j) => ({
    article: `Article ${Math.ceil(Math.random() * 100)}`,
    quantite: Math.ceil(Math.random() * 50),
    prixUnitaire: Math.round(5 + Math.random() * 50),
    montantHT: 0,
  })),
}));
ventesDetail.forEach((v) => {
  v.montantHT = v.quantite * v.prixUnitaire;
  v.montantTTC = Math.round(v.montantHT * 1.19);
  v.lignes.forEach((l) => {
    l.montantHT = l.quantite * l.prixUnitaire;
  });
});
export const clients = Array.from({ length: 30 }, (_, i) => ({
  code: `CL${String(i + 1).padStart(3, "0")}`,
  nom: `Client ${i + 1}`,
  region: REGIONS[Math.floor(Math.random() * REGIONS.length)],
  caTotal: Math.round(50000 + Math.random() * 500000),
  nbCommandes: Math.ceil(Math.random() * 50),
  derniereCommande: `2024-${String(Math.ceil(Math.random() * 12)).padStart(2, "0")}-${String(Math.ceil(Math.random() * 28)).padStart(2, "0")}`,
  soldeImpaye: Math.round(Math.random() * 80000),
  segment: ["Grand compte", "PME", "Petit client"][Math.floor(Math.random() * 3)],
  actif: Math.random() > 0.15,
  nouveau: Math.random() > 0.8,
}));
export const articles = Array.from({ length: 40 }, (_, i) => ({
  code: `ART${String(i + 1).padStart(3, "0")}`,
  designation: `Article ${i + 1}`,
  famille: FAMILLES[Math.floor(Math.random() * FAMILLES.length)],
  qteVendue: Math.ceil(Math.random() * 5000),
  ca: Math.round(10000 + Math.random() * 200000),
  prixMoyen: Math.round(5 + Math.random() * 45),
  marge: Math.round(10 + Math.random() * 30),
}));
export const representants = Array.from({ length: 10 }, (_, i) => ({
  nom: `Représentant ${i + 1}`,
  region: REGIONS[Math.floor(Math.random() * REGIONS.length)],
  caTotal: Math.round(200000 + Math.random() * 800000),
  nbClients: Math.ceil(10 + Math.random() * 40),
  nbCommandes: Math.ceil(50 + Math.random() * 200),
  tauxObjectif: Math.round(60 + Math.random() * 40),
  objectif: 0,
  visites: Math.ceil(100 + Math.random() * 300),
  recouvrement: Math.round(50 + Math.random() * 50),
}));
representants.forEach((r) => {
  r.objectif = Math.round(r.caTotal / (r.tauxObjectif / 100));
});
export const ecritures = Array.from({ length: 40 }, (_, i) => ({
  date: `2024-${String(Math.ceil(Math.random() * 12)).padStart(2, "0")}-${String(Math.ceil(Math.random() * 28)).padStart(2, "0")}`,
  numPiece: `PC${String(i + 1).padStart(5, "0")}`,
  journal: ["Ventes", "Achats", "Banque", "Caisse"][Math.floor(Math.random() * 4)],
  compte: `${Math.ceil(Math.random() * 7)}${String(Math.ceil(Math.random() * 9999)).padStart(4, "0")}`,
  libelle: `Écriture ${i + 1}`,
  debit: Math.random() > 0.5 ? Math.round(Math.random() * 50000) : 0,
  credit: 0,
  solde: 0,
}));
ecritures.forEach((e) => {
  if (e.debit === 0) e.credit = Math.round(Math.random() * 50000);
  e.solde = e.debit - e.credit;
});
export const reglements = Array.from({ length: 40 }, (_, i) => {
  const statut = ["Payé", "Impayé", "Partiel"][Math.floor(Math.random() * 3)];
  const retard = statut === "Payé" ? 0 : Math.ceil(Math.random() * 120);
  return {
    client: `Client ${Math.ceil(Math.random() * 30)}`,
    dateEcheance: `2024-${String(Math.ceil(Math.random() * 12)).padStart(2, "0")}-${String(Math.ceil(Math.random() * 28)).padStart(2, "0")}`,
    montant: Math.round(5000 + Math.random() * 80000),
    modeReglement: ["Espèces", "Chèque", "Virement", "Traite"][Math.floor(Math.random() * 4)],
    statut,
    retard,
  };
});
export const fournisseurs = Array.from({ length: 15 }, (_, i) => ({
  nom: `Fournisseur ${i + 1}`,
  famille: FAMILLES[Math.floor(Math.random() * FAMILLES.length)],
  totalAchats: Math.round(100000 + Math.random() * 500000),
  nbCommandes: Math.ceil(10 + Math.random() * 50),
  delaiMoyen: Math.ceil(3 + Math.random() * 15),
  tauxConformite: Math.round(70 + Math.random() * 30),
}));
export const impayes = Array.from({ length: 30 }, (_, i) => {
  const anciennete = Math.ceil(Math.random() * 150);
  return {
    client: `Client ${Math.ceil(Math.random() * 30)}`,
    region: REGIONS[Math.floor(Math.random() * REGIONS.length)],
    representant: `Rep ${Math.ceil(Math.random() * 10)}`,
    montantImpaye: Math.round(5000 + Math.random() * 100000),
    dateEcheance: `2024-${String(Math.ceil(Math.random() * 12)).padStart(2, "0")}-${String(Math.ceil(Math.random() * 28)).padStart(2, "0")}`,
    anciennete,
    statut:
      anciennete > 90
        ? "Critique"
        : anciennete > 60
          ? "Urgent"
          : anciennete > 30
            ? "Attention"
            : "Récent",
    factures: Array.from({ length: Math.ceil(Math.random() * 3) }, (_, j) => ({
      numero: `FAC-${2024}${String(i * 3 + j + 1).padStart(4, "0")}`,
      montant: Math.round(2000 + Math.random() * 30000),
      date: `2024-${String(Math.ceil(Math.random() * 12)).padStart(2, "0")}-${String(Math.ceil(Math.random() * 28)).padStart(2, "0")}`,
    })),
  };
});
export const encaissementsByMonth = MONTHS.map((m) => ({
  month: m,
  especes: Math.round(50000 + Math.random() * 100000),
  cheque: Math.round(100000 + Math.random() * 200000),
  virement: Math.round(80000 + Math.random() * 150000),
  traite: Math.round(30000 + Math.random() * 80000),
}));
export const achatsByMonth = MONTHS.map((m) => ({
  month: m,
  achats: Math.round(300000 + Math.random() * 400000),
}));
function getSelectedCurrency() {
  try {
    const stored = JSON.parse(localStorage.getItem("finmag-parametres") || "{}");
    const devise = stored?.state?.devise || "TND - Dinar Tunisien";
    if (devise.startsWith("EUR")) return { code: "EUR", rate: 0.3 };
    if (devise.startsWith("USD")) return { code: "USD", rate: 0.33 };
  } catch {}
  return { code: "TND", rate: 1 };
}

export const formatTND = (v) => {
  const { code, rate } = getSelectedCurrency();
  return (
    new Intl.NumberFormat("fr-TN", {
      style: "decimal",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(v * rate) + ` ${code}`
  );
};
export const formatNumber = (v) => new Intl.NumberFormat("fr-TN").format(v);
export const formatPercent = (v) => v.toFixed(1) + "%";
