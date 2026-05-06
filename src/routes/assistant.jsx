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
  Banknote,
  Landmark,
  LayoutDashboard,
  Trash2,
  Copy,
  Check,
  ChevronRight,
  Zap,
} from "lucide-react";
import { caByMonth, articles, clients, impayes, ecritures, formatTND } from "@/data/mockData";

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

function generateAssistantResponse(content) {
  const q = content.toLowerCase();
  const totalCA = caByMonth.reduce((sum, month) => sum + month.ca, 0);
  const stockCritique = articles.filter((a) => a.qteVendue < 500);
  const clientsExposes = clients.filter((c) => c.soldeImpaye > 50000);
  const impayesCritiques = impayes.filter((i) => i.anciennete > 90);
  const anomalies = ecritures.filter((e) => Math.abs(e.solde) > 30000);

  if (q.includes("stock") || q.includes("rupture") || q.includes("article")) {
    const topArticle = [...articles].sort((a, b) => b.qteVendue - a.qteVendue)[0];
    return `Analyse **stocks** depuis les données locales :\n\n- **${stockCritique.length} articles** sont sous le seuil d'alerte simulé\n- Article le plus vendu : **${topArticle?.designation}**\n- Valeur catalogue estimée : **${formatTND(articles.reduce((s, a) => s + a.ca, 0))}**\n\nPriorité : vérifier les articles avec ventes faibles et CA élevé avant réapprovisionnement.`;
  }

  if (q.includes("client") || q.includes("attrition") || q.includes("risque")) {
    return `Analyse **clients** depuis les données locales :\n\n- **${clients.length} clients** suivis\n- **${clientsExposes.length} clients** ont un solde impayé supérieur à 50 000\n- Exposition impayée totale : **${formatTND(clients.reduce((s, c) => s + c.soldeImpaye, 0))}**\n\nPriorité : contacter les clients exposés avant les prochaines échéances.`;
  }

  if (q.includes("trésorerie") || q.includes("tresorerie") || q.includes("impay")) {
    return `Synthèse **trésorerie** depuis les données locales :\n\n- **${impayes.length} créances** en suivi\n- **${impayesCritiques.length} créances** dépassent 90 jours\n- Montant impayé total : **${formatTND(impayes.reduce((s, i) => s + i.montantImpaye, 0))}**\n\nPriorité : traiter les dossiers de plus de 90 jours et les montants les plus élevés.`;
  }

  if (q.includes("fiscal") || q.includes("compta") || q.includes("anomal")) {
    return `Analyse **fiscalité & comptabilité** depuis les données locales :\n\n- **${ecritures.length} écritures** disponibles dans le tableau\n- **${anomalies.length} écritures** ont un solde absolu supérieur à 30 000\n- Journaux couverts : Ventes, Achats, Banque, Caisse\n\nPriorité : filtrer le tableau des écritures et exporter le CSV pour contrôle.`;
  }

  if (q.includes("banque") || q.includes("rapprochement")) {
    return "Synthèse **banque** depuis les données locales :\n\n- Les bordereaux, agios et écarts affichés sont recalculés selon les filtres Banque et Mode\n- Le taux de rapprochement est une moyenne locale de la période sélectionnée\n\nPriorité : utiliser les filtres banque/mode pour isoler les remises non rapprochées.";
  }

  return `Synthèse **MAG Distribution** depuis les données locales :\n\n- CA total estimé : **${formatTND(totalCA)}**\n- Articles sous alerte stock : **${stockCritique.length}**\n- Clients avec solde impayé élevé : **${clientsExposes.length}**\n- Écritures à contrôler : **${anomalies.length}**\n\nVous pouvez me demander un détail sur ventes, stocks, clients, trésorerie, fiscalité ou banque.`;
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
    navigator.clipboard.writeText(msg.content);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const renderContent = (text) => {
    return text.split("\n").map((line, i) => {
      const formatted = line
        .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
        .replace(/_(.*?)_/g, "<em>$1</em>");
      return (
        <span key={i}>
          <span dangerouslySetInnerHTML={{ __html: formatted }} />
          {i < text.split("\n").length - 1 && <br />}
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
        {isUser ? (
          <User size={14} className="text-white" />
        ) : (
          <Bot size={14} className="text-white" />
        )}
      </div>

      <div className={`max-w-[75%] relative ${isUser ? "items-end" : "items-start"} flex flex-col gap-1`}>
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

function AssistantIAPage() {
  const [messages, setMessages] = useState([
    {
      id: 1,
      role: "assistant",
      content:
        "Bonjour ! Je suis votre assistant données pour **MAG Distribution**. Je peux résumer les données locales du tableau de bord, identifier des points à surveiller et préparer des pistes d'analyse.\n\nQue souhaitez-vous explorer aujourd'hui ?",
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
    const content = text || input.trim();
    if (!content) return;

    const userMsg = {
      id: Date.now(),
      role: "user",
      content,
      time: new Date().toLocaleTimeString("fr-TN", { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsTyping(true);

    const delay = 1200 + Math.random() * 800;
    setTimeout(() => {
      const aiMsg = {
        id: Date.now() + 1,
        role: "assistant",
        content: generateAssistantResponse(content),
        time: new Date().toLocaleTimeString("fr-TN", { hour: "2-digit", minute: "2-digit" }),
      };
      setIsTyping(false);
      setMessages((prev) => [...prev, aiMsg]);
    }, delay);
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const clearChat = () => {
    setMessages([
      {
        id: Date.now(),
        role: "assistant",
        content: "Conversation réinitialisée. Comment puis-je vous aider ?",
        time: new Date().toLocaleTimeString("fr-TN", { hour: "2-digit", minute: "2-digit" }),
      },
    ]);
  };

  const showSuggestions = messages.length <= 1;

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
              <span className="text-[11px] text-text-dim">Basé sur les données locales MAG Distribution</span>
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

        {/* Suggestions */}
        {showSuggestions && !isTyping && (
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
                  <div>
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
