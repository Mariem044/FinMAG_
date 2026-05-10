import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef, useEffect } from "react";
import {
  Sparkles,
  Send,
  User,
  Bot,
  TrendingUp,
  Wallet,
  Boxes,
  Users,
  Receipt,
  Landmark,
  Trash2,
  Copy,
  Check,
  ChevronRight,
  Zap,
} from "lucide-react";
import { formatTND } from "@/lib/dashboardConstants";
import { api } from "@/lib/api";
import { useApiResource } from "@/hooks/useApiResource";

export const Route = createFileRoute("/assistant")({
  component: AssistantIAPage,
});

const SUGGESTIONS = [
  {
    icon: TrendingUp,
    label: "CA & Ventes",
    text: "Quel est le chiffre d'affaires total et les meilleures familles de produits ?",
  },
  {
    icon: Wallet,
    label: "Trésorerie",
    text: "Analyse l'état actuel de la trésorerie et les créances impayées.",
  },
  {
    icon: Boxes,
    label: "Stocks",
    text: "Quels articles sont en rupture de stock ou sous le seuil d'alerte ?",
  },
  {
    icon: Users,
    label: "Clients",
    text: "Identifie les clients à risque d'attrition et les top clients par CA.",
  },
  {
    icon: Receipt,
    label: "Fiscalité",
    text: "Résume les anomalies comptables détectées ce mois-ci.",
  },
  {
    icon: Landmark,
    label: "Banque",
    text: "Quel est le taux de rapprochement bancaire actuel ?",
  },
];

/**
 * generateAssistantResponse — builds a text response from local DW data.
 *
 * Expected `data` shape (from /api/assistant/summary):
 * {
 *   kpis:      { ca_total, nb_commandes, nb_clients_actifs, taux_recouvrement, marge_brute_pct },
 *   caByMonth: [{ month, ca, objectif, caN1 }],
 *   articles:  [{ designation, famille, qteVendue, stock, ca, prixMoyen, dsi }],
 *   clients:   [{ code, nom, segment, region, actif, soldeImpaye, nbCommandes }],
 *   impayes:   [{ clientCode, montantImpaye, anciennete }],
 *   ecritures: [{ date, numPiece, journal, compte, libelle, debit, credit, solde }],
 * }
 */
function generateAssistantResponse(content, data = {}) {
  const q = content.toLowerCase();

  // Safe destructuring with defaults for every array
  const caByMonth = Array.isArray(data.caByMonth) ? data.caByMonth : [];
  const articles = Array.isArray(data.articles) ? data.articles : [];
  const clients = Array.isArray(data.clients) ? data.clients : [];
  const impayes = Array.isArray(data.impayes) ? data.impayes : [];
  const ecritures = Array.isArray(data.ecritures) ? data.ecritures : [];
  const kpis = data.kpis || {};

  const totalCA = kpis.ca_total || caByMonth.reduce((sum, m) => sum + (m.ca || 0), 0);

  const stockCritique = articles.filter((a) => (a.qteVendue || 0) < 500);
  const clientsExposes = clients.filter((c) => (c.soldeImpaye || 0) > 50000);
  const impayesCritiques = impayes.filter((i) => (i.anciennete || 0) > 90);
  const anomalies = ecritures.filter((e) => Math.abs(e.solde || 0) > 30000);

  if (q.includes("stock") || q.includes("rupture") || q.includes("article")) {
    const topArticle = [...articles].sort((a, b) => (b.qteVendue || 0) - (a.qteVendue || 0))[0];
    const totalStockCA = articles.reduce((s, a) => s + (a.ca || 0), 0);
    return (
      `Analyse **stocks** depuis les données DW :\n\n` +
      `- **${stockCritique.length} articles** sont sous le seuil d'alerte (ventes < 500 u.)\n` +
      (topArticle ? `- Article le plus vendu : **${topArticle.designation}**\n` : "") +
      `- Valeur catalogue estimée : **${formatTND(totalStockCA)}**\n\n` +
      `Priorité : vérifier les articles avec ventes faibles et CA élevé avant réapprovisionnement.`
    );
  }

  if (q.includes("client") || q.includes("attrition") || q.includes("risque")) {
    const totalImpaye = clients.reduce((s, c) => s + (c.soldeImpaye || 0), 0);
    return (
      `Analyse **clients** depuis les données DW :\n\n` +
      `- **${clients.length} clients** suivis\n` +
      `- **${clientsExposes.length} clients** ont un solde impayé > 50 000 DT\n` +
      `- Exposition impayée totale : **${formatTND(totalImpaye)}**\n\n` +
      `Priorité : contacter les clients exposés avant les prochaines échéances.`
    );
  }

  if (q.includes("trésorerie") || q.includes("tresorerie") || q.includes("impay")) {
    const totalMontantImpaye = impayes.reduce((s, i) => s + (i.montantImpaye || 0), 0);
    return (
      `Synthèse **trésorerie** depuis les données DW :\n\n` +
      `- **${impayes.length} créances** en suivi\n` +
      `- **${impayesCritiques.length} créances** dépassent 90 jours\n` +
      `- Montant impayé total : **${formatTND(totalMontantImpaye)}**\n\n` +
      `Priorité : traiter les dossiers > 90 jours et les montants les plus élevés.`
    );
  }

  if (q.includes("fiscal") || q.includes("compta") || q.includes("anomal")) {
    return (
      `Analyse **fiscalité & comptabilité** depuis les données DW :\n\n` +
      `- **${ecritures.length} écritures** disponibles\n` +
      `- **${anomalies.length} écritures** ont un solde absolu > 30 000 DT\n` +
      `- Journaux couverts : Ventes, Achats, Banque, Caisse\n\n` +
      `Priorité : filtrer le tableau des écritures et exporter le CSV pour contrôle.`
    );
  }

  if (q.includes("banque") || q.includes("rapprochement")) {
    return (
      `Synthèse **banque** depuis les données DW :\n\n` +
      `- Les bordereaux, agios et écarts sont calculés selon les filtres Banque / Mode\n` +
      `- Le taux de rapprochement est une moyenne de la période sélectionnée\n\n` +
      `Priorité : utiliser les filtres banque/mode pour isoler les remises non rapprochées.`
    );
  }

  // Default summary
  return (
    `Synthèse **MAG Distribution** depuis les données DW :\n\n` +
    `- CA total estimé : **${formatTND(totalCA)}**\n` +
    `- Articles sous alerte stock : **${stockCritique.length}**\n` +
    `- Clients avec solde impayé élevé : **${clientsExposes.length}**\n` +
    `- Écritures à contrôler : **${anomalies.length}**\n\n` +
    `Vous pouvez me demander un détail sur : ventes, stocks, clients, trésorerie, fiscalité ou banque.`
  );
}

function TypingIndicator() {
  return (
    <div className="flex items-end gap-3">
      <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-primary to-primary/70 flex items-center justify-center flex-shrink-0 shadow-lg shadow-primary/30">
        <Bot size={14} className="text-white" />
      </div>
      <div className="bg-card border border-border/60 rounded-2xl rounded-bl-sm px-4 py-3">
        <div className="flex gap-1.5 items-center h-4">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="w-1.5 h-1.5 rounded-full bg-primary/60 animate-bounce"
              style={{ animationDelay: `${i * 150}ms`, animationDuration: "900ms" }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function MessageBubble({ msg }) {
  const [copied, setCopied] = useState(false);
  const isUser = msg.role === "user";

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.content).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const renderContent = (text) => {
    return text.split("\n").map((line, i, arr) => {
      const formatted = line
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
        .replace(/_(.*?)_/g, "<em>$1</em>");
      return (
        <span key={i}>
          <span dangerouslySetInnerHTML={{ __html: formatted }} />
          {i < arr.length - 1 && <br />}
        </span>
      );
    });
  };

  return (
    <div className={`flex items-end gap-3 group ${isUser ? "flex-row-reverse" : ""}`}>
      <div
        className={`w-8 h-8 rounded-xl flex items-center justify-center flex-shrink-0 shadow-md ${
          isUser
            ? "bg-gradient-to-br from-slate-600 to-slate-700 shadow-slate-900/30"
            : "bg-gradient-to-br from-primary to-primary/70 shadow-primary/30"
        }`}
      >
        {isUser ? <User size={14} className="text-white" /> : <Bot size={14} className="text-white" />}
      </div>

      <div className={`max-w-[75%] relative flex flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`px-4 py-3 rounded-2xl text-[13px] leading-relaxed ${
            isUser
              ? "bg-primary text-white rounded-br-sm shadow-lg shadow-primary/25"
              : "bg-card border border-border/60 text-foreground rounded-bl-sm shadow-sm"
          }`}
        >
          {renderContent(msg.content)}
        </div>
        <div className={`flex items-center gap-2 px-1 ${isUser ? "flex-row-reverse" : ""}`}>
          <span className="text-[10px] text-text-dim">{msg.time}</span>
          {!isUser && (
            <button
              onClick={handleCopy}
              className="opacity-0 group-hover:opacity-100 transition-opacity text-text-dim hover:text-foreground"
            >
              {copied ? <Check size={11} className="text-green-400" /> : <Copy size={11} />}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── INITIAL_DATA is module-level so its reference is stable ─────────────────
const ASSISTANT_INITIAL = {
  kpis: {},
  caByMonth: [],
  articles: [],
  clients: [],
  impayes: [],
  ecritures: [],
};

function AssistantIAPage() {
  const { data: assistantData } = useApiResource(api.assistantSummary, ASSISTANT_INITIAL);

  const [messages, setMessages] = useState(() => [
    {
      id: 1,
      role: "assistant",
      content:
        "Bonjour ! Je suis votre assistant données pour **MAG Distribution**. Je peux résumer les données du tableau de bord, identifier des points à surveiller et préparer des pistes d'analyse.\n\nQue souhaitez-vous explorer aujourd'hui ?",
      time: new Date().toLocaleTimeString("fr-TN", { hour: "2-digit", minute: "2-digit" }),
    },
  ]);
  const [input, setInput] = useState("");
  const [isTyping, setIsTyping] = useState(false);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isTyping]);

  const sendMessage = (text) => {
    const content = (text || input).trim();
    if (!content) return;

    const now = new Date().toLocaleTimeString("fr-TN", { hour: "2-digit", minute: "2-digit" });
    const userMsg = { id: Date.now(), role: "user", content, time: now };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsTyping(true);

    const delay = Math.min(1200 + content.length * 12, 2000);
    setTimeout(() => {
      const aiContent = generateAssistantResponse(content, assistantData);
      const aiTime = new Date().toLocaleTimeString("fr-TN", { hour: "2-digit", minute: "2-digit" });
      setIsTyping(false);
      setMessages((prev) => [...prev, { id: Date.now() + 1, role: "assistant", content: aiContent, time: aiTime }]);
    }, delay);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const clearChat = () => {
    const now = new Date().toLocaleTimeString("fr-TN", { hour: "2-digit", minute: "2-digit" });
    setMessages([
      { id: Date.now(), role: "assistant", content: "Conversation réinitialisée. Comment puis-je vous aider ?", time: now },
    ]);
  };

  const showSuggestions = messages.length <= 1 && !isTyping;

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center shadow-lg shadow-primary/30">
            <Sparkles size={18} className="text-white" />
          </div>
          <div>
            <h1 className="text-[18px] font-bold text-foreground leading-none">Assistant données</h1>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
              <span className="text-[11px] text-text-dim">Basé sur les données MAG Distribution</span>
            </div>
          </div>
        </div>
        <button
          onClick={clearChat}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-border text-text-dim hover:text-foreground hover:border-border/80 text-[12px] transition-colors"
        >
          <Trash2 size={12} />
          Effacer
        </button>
      </div>

      {/* Chat area */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1 pb-4">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}
        {isTyping && <TypingIndicator />}
        <div ref={messagesEndRef} />

        {showSuggestions && (
          <div className="mt-6">
            <p className="text-[11px] text-text-dim font-semibold uppercase tracking-wider mb-3 flex items-center gap-1.5">
              <Zap size={11} className="text-primary" />
              Suggestions rapides
            </p>
            <div className="grid grid-cols-2 md:grid-cols-3 gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s.label}
                  onClick={() => sendMessage(s.text)}
                  className="flex items-start gap-2.5 p-3 rounded-xl border border-border/60 bg-card hover:border-primary/40 hover:bg-primary/5 text-left transition-all duration-200 group"
                >
                  <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 group-hover:bg-primary/20 transition-colors">
                    <s.icon size={13} className="text-primary" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold text-foreground leading-none mb-1">{s.label}</p>
                    <p className="text-[11px] text-text-dim leading-relaxed line-clamp-2">{s.text}</p>
                  </div>
                  <ChevronRight size={12} className="text-text-dim flex-shrink-0 mt-1 opacity-0 group-hover:opacity-100 transition-opacity ml-auto" />
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Input area */}
      <div className="flex-shrink-0 mt-2">
        <div className="flex gap-2 p-2 bg-card border border-border/60 rounded-2xl shadow-lg">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Posez votre question sur les données MAG Distribution..."
            rows={1}
            className="flex-1 bg-transparent text-[13px] text-foreground placeholder:text-text-dim outline-none resize-none px-2 py-1.5 leading-relaxed max-h-32"
            style={{ minHeight: "36px" }}
            onInput={(e) => {
              e.target.style.height = "auto";
              e.target.style.height = Math.min(e.target.scrollHeight, 128) + "px";
            }}
          />
          <button
            onClick={() => sendMessage()}
            disabled={!input.trim() || isTyping}
            className="w-9 h-9 rounded-xl bg-primary flex items-center justify-center flex-shrink-0 self-end shadow-md shadow-primary/30 hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-200 hover:scale-105 active:scale-95"
          >
            <Send size={15} className="text-white" />
          </button>
        </div>
        <p className="text-[10px] text-text-dim text-center mt-1.5">
          Entrée pour envoyer · Maj+Entrée pour nouvelle ligne
        </p>
      </div>
    </div>
  );
}