import { createFileRoute } from "@tanstack/react-router";
import { useState, useRef, useEffect } from "react";
import {
  AlertCircle,
  ArrowUpRight,
  BarChart3,
  Bot,
  Check,
  ChevronRight,
  Clock3,
  Copy,
  FileText,
  Landmark,
  Mic,
  Paperclip,
  RefreshCw,
  Send,
  ShieldAlert,
  Sparkles,
  Square,
  TrendingUp,
  Trash2,
  User,
  Users,
  Wallet,
  Warehouse,
  Zap,
} from "lucide-react";

export const Route = createFileRoute("/assistant")({
  component: AssistantIAPage,
});

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const QUICK_ACTION_GROUPS = [
  {
    title: "Finance",
    items: [
      {
        icon: TrendingUp,
        label: "Analyser CA",
        text: "Analyse le chiffre d'affaires, les tendances et les familles de produits les plus performantes.",
      },
      {
        icon: Wallet,
        label: "Tresorerie",
        text: "Analyse la tresorerie, les encaissements, les impayes et les priorites de recouvrement.",
      },
    ],
  },
  {
    title: "Operations",
    items: [
      {
        icon: Warehouse,
        label: "Stock critique",
        text: "Quels articles sont en rupture ou sous le seuil d'alerte ? Donne les actions recommandees.",
      },
      {
        icon: Users,
        label: "Clients a risque",
        text: "Identifie les clients a risque, les top clients par CA et les signaux d'attrition.",
      },
    ],
  },
  {
    title: "Controle",
    items: [
      {
        icon: ShieldAlert,
        label: "Anomalies",
        text: "Detecte les anomalies comptables, fiscales ou commerciales a surveiller ce mois-ci.",
      },
      {
        icon: Landmark,
        label: "Banque",
        text: "Analyse le taux de rapprochement bancaire et les remises non rapprochees.",
      },
    ],
  },
];

const LIVE_INSIGHTS = [
  { label: "CA annuel", value: "4.82M DT", trend: "+8.4%", tone: "positive" },
  { label: "Encaissements", value: "1.26M DT", trend: "+3.1%", tone: "positive" },
  { label: "Impayes", value: "318K DT", trend: "12 alertes", tone: "warning" },
  { label: "Stock critique", value: "27", trend: "a traiter", tone: "danger" },
];

const RECENT_THREADS = [
  "Synthese tresorerie",
  "Clients a risque",
  "Stock sous seuil",
  "Rapprochement banque",
];

const SAMPLE_INSIGHT = {
  title: "Vue executive",
  summary: "Les indicateurs critiques sont suivis en direct depuis le data warehouse MAG.",
  kpis: [
    { label: "CA", value: "4.82M DT", trend: "+8.4%" },
    { label: "Recouvrement", value: "82%", trend: "+4 pts" },
    { label: "Alertes stock", value: "27", trend: "urgent" },
  ],
  alerts: ["3 clients concentrent 42% des impayes", "7 articles sont sous le seuil critique"],
};

function getTime() {
  return new Date().toLocaleTimeString("fr-TN", { hour: "2-digit", minute: "2-digit" });
}

function TypingIndicator() {
  return (
    <div className="flex items-end gap-3 animate-in fade-in slide-in-from-bottom-2 duration-200">
      <AssistantAvatar />
      <div className="rounded-2xl rounded-bl-md border border-border/70 bg-card px-4 py-3 shadow-sm">
        <div className="flex h-4 items-center gap-1.5">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="h-1.5 w-1.5 animate-bounce rounded-full bg-primary/70"
              style={{ animationDelay: `${i * 140}ms`, animationDuration: "900ms" }}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

function AssistantAvatar() {
  return (
    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-lg shadow-primary/25">
      <Bot size={16} />
    </div>
  );
}

function UserAvatar() {
  return (
    <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-foreground text-background shadow-md">
      <User size={15} />
    </div>
  );
}

function renderMarkdown(text) {
  return text.split("\n").map((line, i, arr) => {
    const formatted = line
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/_(.*?)_/g, "<em>$1</em>")
      .replace(
        /`(.*?)`/g,
        "<code style='background:rgba(79,141,253,.14);padding:1px 5px;border-radius:4px;font-size:11px'>$1</code>",
      );
    return (
      <span key={i}>
        <span dangerouslySetInnerHTML={{ __html: formatted }} />
        {i < arr.length - 1 && <br />}
      </span>
    );
  });
}

function StatusPill({ llmStatus }) {
  if (llmStatus.llm_ready === null) {
    return (
      <span className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-[11px] text-text-dim">
        <RefreshCw size={11} className="animate-spin text-primary" />
        Connexion
      </span>
    );
  }

  if (llmStatus.llm_ready) {
    return (
      <span className="inline-flex items-center gap-2 rounded-full border border-green-500/25 bg-green-500/10 px-3 py-1 text-[11px] text-green-400">
        <span className="h-1.5 w-1.5 rounded-full bg-green-400 shadow-[0_0_0_4px_rgba(34,197,94,.14)]" />
        {llmStatus.model || "Gemini 1.5 Flash"}
      </span>
    );
  }

  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-amber-500/25 bg-amber-500/10 px-3 py-1 text-[11px] text-amber-400">
      <AlertCircle size={11} />
      Cle API manquante
    </span>
  );
}

function AssistantHeader({ llmStatus, onClear }) {
  return (
    <div className="flex flex-col gap-4 border-b border-border/70 bg-background/95 px-4 py-4 backdrop-blur md:px-6 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex items-center gap-3">
        <div className="flex h-11 w-11 items-center justify-center rounded-2xl bg-primary text-primary-foreground shadow-lg shadow-primary/25">
          <Sparkles size={19} />
        </div>
        <div>
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-[18px] font-bold leading-none text-foreground">FinMAG AI Copilot</h1>
            <span className="rounded-full border border-primary/20 bg-primary/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-primary">
              Live DW
            </span>
          </div>
          <p className="mt-1 text-[12px] text-text-dim">
            Analyse financiere, risques et recommandations connectees aux donnees MAG.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <StatusPill llmStatus={llmStatus} />
        <span className="inline-flex items-center gap-2 rounded-full border border-border bg-card px-3 py-1 text-[11px] text-text-dim">
          <Clock3 size={11} className="text-primary" />
          Sync {getTime()}
        </span>
        <button
          onClick={onClear}
          className="inline-flex h-8 items-center gap-2 rounded-lg border border-border bg-card px-3 text-[12px] text-text-dim transition-all duration-200 hover:border-primary/40 hover:text-foreground"
        >
          <Trash2 size={13} />
          Effacer
        </button>
      </div>
    </div>
  );
}

function WorkspaceRail({ onSelect, isStreaming }) {
  return (
    <aside className="hidden min-h-0 border-r border-border/70 bg-card/45 lg:flex lg:flex-col">
      <div className="border-b border-border/70 p-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-dim">
          Actions rapides
        </p>
      </div>

      <div className="min-h-0 flex-1 space-y-5 overflow-y-auto p-4">
        {QUICK_ACTION_GROUPS.map((group) => (
          <section key={group.title}>
            <p className="mb-2 text-[11px] font-semibold text-text-muted">{group.title}</p>
            <div className="space-y-2">
              {group.items.map((item) => (
                <button
                  key={item.label}
                  onClick={() => onSelect(item.text)}
                  disabled={isStreaming}
                  className="group flex w-full items-center gap-3 rounded-xl border border-border/60 bg-background/55 p-3 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:bg-primary/5 hover:shadow-lg hover:shadow-primary/5 disabled:cursor-not-allowed disabled:opacity-50"
                >
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary transition-colors group-hover:bg-primary group-hover:text-primary-foreground">
                    <item.icon size={15} />
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-[12px] font-semibold text-foreground">
                      {item.label}
                    </span>
                    <span className="block truncate text-[11px] text-text-dim">{item.text}</span>
                  </span>
                  <ChevronRight
                    size={14}
                    className="text-text-dim opacity-0 transition-opacity group-hover:opacity-100"
                  />
                </button>
              ))}
            </div>
          </section>
        ))}
      </div>

      <div className="border-t border-border/70 p-4">
        <p className="mb-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-text-dim">
          Historique
        </p>
        <div className="space-y-1">
          {RECENT_THREADS.map((thread) => (
            <button
              key={thread}
              className="flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-[12px] text-text-muted transition-colors hover:bg-surface-hover hover:text-foreground"
            >
              <FileText size={13} />
              <span className="truncate">{thread}</span>
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}

function InsightPreview() {
  return (
    <div className="mt-3 rounded-xl border border-border/70 bg-background/55 p-3">
      <div className="mb-3 flex items-center justify-between">
        <div>
          <p className="text-[12px] font-semibold text-foreground">{SAMPLE_INSIGHT.title}</p>
          <p className="text-[11px] text-text-dim">{SAMPLE_INSIGHT.summary}</p>
        </div>
        <BarChart3 size={16} className="text-primary" />
      </div>
      <div className="grid gap-2 sm:grid-cols-3">
        {SAMPLE_INSIGHT.kpis.map((kpi) => (
          <div key={kpi.label} className="rounded-lg border border-border/60 bg-card p-3">
            <p className="text-[10px] uppercase tracking-[0.12em] text-text-dim">{kpi.label}</p>
            <p className="mt-1 text-[16px] font-bold text-foreground">{kpi.value}</p>
            <p className="mt-1 text-[11px] text-primary">{kpi.trend}</p>
          </div>
        ))}
      </div>
      <div className="mt-3 space-y-2">
        {SAMPLE_INSIGHT.alerts.map((alert) => (
          <div
            key={alert}
            className="flex items-center gap-2 rounded-lg bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300"
          >
            <AlertCircle size={13} />
            <span>{alert}</span>
          </div>
        ))}
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
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <div
      className={`group flex gap-3 animate-in fade-in slide-in-from-bottom-2 duration-200 ${
        isUser ? "justify-end" : "justify-start"
      }`}
    >
      {!isUser && <AssistantAvatar />}

      <div className={`max-w-[min(760px,82%)] ${isUser ? "items-end" : "items-start"}`}>
        <div
          className={`rounded-2xl px-4 py-3 text-[13px] leading-relaxed shadow-sm ${
            isUser
              ? "rounded-br-md bg-primary text-primary-foreground shadow-primary/20"
              : "rounded-bl-md border border-border/70 bg-card text-foreground"
          }`}
        >
          {msg.streaming ? (
            <span>
              {renderMarkdown(msg.content)}
              <span className="ml-0.5 inline-block h-3.5 w-0.5 animate-pulse bg-primary align-middle" />
            </span>
          ) : (
            renderMarkdown(msg.content)
          )}
          {!isUser && msg.insight && <InsightPreview />}
        </div>

        <div className={`mt-1 flex items-center gap-2 px-1 ${isUser ? "justify-end" : ""}`}>
          <span className="text-[10px] text-text-dim">{msg.time}</span>
          {!isUser && !msg.streaming && (
            <button
              onClick={handleCopy}
              className="text-text-dim opacity-0 transition-all duration-200 hover:text-foreground group-hover:opacity-100"
              aria-label="Copier la reponse"
            >
              {copied ? <Check size={12} className="text-green-400" /> : <Copy size={12} />}
            </button>
          )}
        </div>
      </div>

      {isUser && <UserAvatar />}
    </div>
  );
}

function EmptyPromptStrip({ onSelect, isStreaming }) {
  const prompts = QUICK_ACTION_GROUPS.flatMap((group) => group.items).slice(0, 4);

  return (
    <div className="grid gap-2 md:grid-cols-4">
      {prompts.map((item) => (
        <button
          key={item.label}
          onClick={() => onSelect(item.text)}
          disabled={isStreaming}
          className="group rounded-xl border border-border/70 bg-card p-3 text-left transition-all duration-200 hover:-translate-y-0.5 hover:border-primary/40 hover:bg-primary/5 disabled:cursor-not-allowed disabled:opacity-50"
        >
          <div className="mb-2 flex items-center justify-between">
            <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary/10 text-primary">
              <item.icon size={14} />
            </span>
            <ArrowUpRight
              size={13}
              className="text-text-dim opacity-0 transition-opacity group-hover:opacity-100"
            />
          </div>
          <p className="text-[12px] font-semibold text-foreground">{item.label}</p>
          <p className="mt-1 line-clamp-2 text-[11px] leading-relaxed text-text-dim">{item.text}</p>
        </button>
      ))}
    </div>
  );
}

function ChatInput({
  input,
  setInput,
  onSend,
  isStreaming,
  onStop,
  inputRef,
  onKeyDown,
}) {
  return (
    <div className="border-t border-border/70 bg-background/95 p-4 backdrop-blur md:p-5">
      <div className="mx-auto max-w-4xl">
        <div className="flex items-end gap-2 rounded-2xl border border-border/70 bg-card p-2 shadow-2xl shadow-black/10 transition-all duration-200 focus-within:border-primary/50 focus-within:shadow-primary/10">
          <button
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-text-dim transition-colors hover:bg-surface-hover hover:text-foreground"
            aria-label="Joindre un fichier"
          >
            <Paperclip size={17} />
          </button>
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={
              isStreaming
                ? "FinMAG analyse les donnees..."
                : "Demandez une analyse CA, tresorerie, stock, clients ou anomalies..."
            }
            rows={1}
            disabled={isStreaming}
            className="max-h-36 min-h-10 flex-1 resize-none bg-transparent px-1 py-2 text-[13px] leading-relaxed text-foreground outline-none placeholder:text-text-dim disabled:opacity-60"
            onInput={(e) => {
              e.target.style.height = "auto";
              e.target.style.height = Math.min(e.target.scrollHeight, 144) + "px";
            }}
          />
          <button
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-text-dim transition-colors hover:bg-surface-hover hover:text-foreground"
            aria-label="Dicter une question"
          >
            <Mic size={17} />
          </button>
          {isStreaming ? (
            <button
              onClick={onStop}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-foreground text-background shadow-md transition-all duration-200 hover:scale-105 active:scale-95"
              aria-label="Arreter la reponse"
            >
              <Square size={14} />
            </button>
          ) : (
            <button
              onClick={() => onSend()}
              disabled={!input.trim()}
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-lg shadow-primary/25 transition-all duration-200 hover:scale-105 hover:bg-primary/90 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40"
              aria-label="Envoyer"
            >
              <Send size={16} />
            </button>
          )}
        </div>
        <div className="mt-2 flex flex-wrap items-center justify-center gap-x-4 gap-y-1 text-[10px] text-text-dim">
          <span>Entree pour envoyer</span>
          <span>Maj+Entree pour nouvelle ligne</span>
          <span>Reponses basees sur les donnees live</span>
        </div>
      </div>
    </div>
  );
}

function LiveInsightsPanel() {
  return (
    <aside className="hidden min-h-0 border-l border-border/70 bg-card/45 xl:flex xl:flex-col">
      <div className="border-b border-border/70 p-4">
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-text-dim">
          Live Insights
        </p>
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
        <section className="rounded-2xl border border-border/70 bg-background/55 p-4">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="text-[13px] font-semibold text-foreground">KPI prioritaires</p>
              <p className="text-[11px] text-text-dim">Donnees consolidees</p>
            </div>
            <Zap size={15} className="text-primary" />
          </div>
          <div className="space-y-3">
            {LIVE_INSIGHTS.map((item) => (
              <div key={item.label} className="rounded-xl border border-border/60 bg-card p-3">
                <div className="flex items-center justify-between gap-2">
                  <p className="text-[11px] text-text-dim">{item.label}</p>
                  <span
                    className={`rounded-full px-2 py-0.5 text-[10px] ${
                      item.tone === "positive"
                        ? "bg-green-500/10 text-green-400"
                        : item.tone === "warning"
                          ? "bg-amber-500/10 text-amber-300"
                          : "bg-red-500/10 text-red-300"
                    }`}
                  >
                    {item.trend}
                  </span>
                </div>
                <p className="mt-1 text-[18px] font-bold text-foreground">{item.value}</p>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-border/70 bg-background/55 p-4">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <p className="text-[13px] font-semibold text-foreground">Signal recouvrement</p>
              <p className="text-[11px] text-text-dim">Top risques clients</p>
            </div>
            <Users size={15} className="text-primary" />
          </div>
          <div className="space-y-2">
            {["Client A", "Client B", "Client C"].map((client, index) => (
              <div key={client} className="flex items-center justify-between rounded-lg bg-card p-3">
                <div>
                  <p className="text-[12px] font-semibold text-foreground">{client}</p>
                  <p className="text-[10px] text-text-dim">{index + 2} factures ouvertes</p>
                </div>
                <span className="text-[11px] font-semibold text-amber-300">
                  {92 - index * 13}K DT
                </span>
              </div>
            ))}
          </div>
        </section>

        <section className="rounded-2xl border border-border/70 bg-background/55 p-4">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-[13px] font-semibold text-foreground">Tendance CA</p>
            <BarChart3 size={15} className="text-primary" />
          </div>
          <div className="flex h-28 items-end gap-2">
            {[42, 58, 47, 72, 66, 88, 78, 92].map((height, index) => (
              <div key={index} className="flex flex-1 items-end rounded-full bg-primary/10">
                <div
                  className="w-full rounded-full bg-primary/80 transition-all duration-300"
                  style={{ height: `${height}%` }}
                />
              </div>
            ))}
          </div>
        </section>
      </div>
    </aside>
  );
}

function AssistantIAPage() {
  const [messages, setMessages] = useState(() => [
    {
      id: 1,
      role: "assistant",
      content:
        "Bonjour. Je suis **FinMAG AI**, votre copilot financier connecte au data warehouse MAG Distribution.\n\nJe peux analyser le CA, la tresorerie, les stocks, les clients, la fiscalite et les alertes operationnelles.",
      time: getTime(),
      streaming: false,
      insight: true,
    },
  ]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [llmStatus, setLlmStatus] = useState({ llm_ready: null, model: null });
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const abortRef = useRef(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    fetch(`${API_BASE}/api/assistant/status`)
      .then((r) => r.json())
      .then(setLlmStatus)
      .catch(() => setLlmStatus({ llm_ready: false, model: null }));
  }, []);

  const stopStreaming = () => {
    abortRef.current?.abort();
    setIsStreaming(false);
  };

  const sendMessage = async (text) => {
    const content = (text || input).trim();
    if (!content || isStreaming) return;

    const userMsg = { id: Date.now(), role: "user", content, time: getTime(), streaming: false };

    const historyForApi = [
      ...messages.filter((m) => !m.streaming).map((m) => ({ role: m.role, content: m.content })),
      { role: "user", content },
    ];

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsStreaming(true);

    const assistantId = Date.now() + 1;
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: "assistant", content: "", time: getTime(), streaming: true },
    ]);

    try {
      const controller = new AbortController();
      abortRef.current = controller;

      const res = await fetch(`${API_BASE}/api/assistant/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: historyForApi }),
        signal: controller.signal,
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          if (!line.startsWith("data: ")) continue;
          const chunk = line.slice(6);
          if (chunk === "[DONE]") break;

          setMessages((prev) =>
            prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + chunk } : m)),
          );
        }
      }
    } catch (err) {
      if (err.name !== "AbortError") {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  content:
                    m.content ||
                    "Impossible de contacter l'IA. Verifiez que le serveur API est demarre et que GEMINI_API_KEY est configure dans `etl/.env`.",
                }
              : m,
          ),
        );
      }
    } finally {
      setMessages((prev) =>
        prev.map((m) => (m.id === assistantId ? { ...m, streaming: false, time: getTime() } : m)),
      );
      setIsStreaming(false);
      abortRef.current = null;
    }
  };

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  };

  const clearChat = () => {
    abortRef.current?.abort();
    setMessages([
      {
        id: Date.now(),
        role: "assistant",
        content: "Conversation reinitialisee. Quelle analyse voulez-vous lancer ?",
        time: getTime(),
        streaming: false,
        insight: true,
      },
    ]);
    setIsStreaming(false);
  };

  const showSuggestions = messages.length <= 1 && !isStreaming;

  return (
    <div className="-mx-4 -mb-8 -mt-2 flex h-[calc(100vh-5.5rem)] flex-col overflow-hidden rounded-2xl border border-border/70 bg-background shadow-2xl shadow-black/10 md:-mx-6 lg:-mx-8">
      <AssistantHeader llmStatus={llmStatus} onClear={clearChat} />

      <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-[280px_minmax(0,1fr)] xl:grid-cols-[280px_minmax(0,1fr)_320px]">
        <WorkspaceRail onSelect={sendMessage} isStreaming={isStreaming} />

        <main className="flex min-h-0 flex-col bg-background">
          <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 md:px-6">
            <div className="mx-auto flex max-w-4xl flex-col gap-4">
              {messages.map((msg) => (
                <MessageBubble key={msg.id} msg={msg} />
              ))}
              {isStreaming && messages[messages.length - 1]?.role !== "assistant" && (
                <TypingIndicator />
              )}
              {showSuggestions && <EmptyPromptStrip onSelect={sendMessage} isStreaming={isStreaming} />}
              <div ref={messagesEndRef} />
            </div>
          </div>

          <ChatInput
            input={input}
            setInput={setInput}
            onSend={sendMessage}
            isStreaming={isStreaming}
            onStop={stopStreaming}
            inputRef={inputRef}
            onKeyDown={handleKeyDown}
          />
        </main>

        <LiveInsightsPanel />
      </div>
    </div>
  );
}
