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
  AlertCircle,
  Cpu,
} from "lucide-react";

export const Route = createFileRoute("/assistant")({
  component: AssistantIAPage,
});

const API_BASE = import.meta.env.VITE_API_URL || "http://localhost:8000";

const SUGGESTIONS = [
  {
    icon: TrendingUp,
    label: "CA & Ventes",
    text: "Quel est le chiffre d'affaires total ? Quelles familles de produits performent le mieux ?",
  },
  {
    icon: Wallet,
    label: "Tresorerie",
    text: "Analyse l'etat de la tresorerie et les creances impayees. Quelles actions recommandes-tu ?",
  },
  {
    icon: Boxes,
    label: "Stocks",
    text: "Quels articles sont en rupture ou sous le seuil d'alerte ? Donne-moi des recommandations.",
  },
  {
    icon: Users,
    label: "Clients a risque",
    text: "Identifie les clients a risque d'attrition et les top clients par CA.",
  },
  {
    icon: Receipt,
    label: "Anomalies",
    text: "Y a-t-il des anomalies comptables ou fiscales a surveiller ce mois-ci ?",
  },
  {
    icon: Landmark,
    label: "Banque",
    text: "Quel est le taux de rapprochement bancaire actuel et quelles remises ne sont pas rapprochees ?",
  },
];

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

function renderMarkdown(text) {
  return text.split("\n").map((line, i, arr) => {
    const formatted = line
      .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
      .replace(/_(.*?)_/g, "<em>$1</em>")
      .replace(
        /`(.*?)`/g,
        "<code style='background:rgba(99,102,241,.15);padding:1px 5px;border-radius:4px;font-size:11px'>$1</code>",
      );
    return (
      <span key={i}>
        <span dangerouslySetInnerHTML={{ __html: formatted }} />
        {i < arr.length - 1 && <br />}
      </span>
    );
  });
}

function MessageBubble({ msg }) {
  const [copied, setCopied] = useState(false);
  const isUser = msg.role === "user";

  const handleCopy = () => {
    navigator.clipboard.writeText(msg.content).catch(() => {});
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
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

      <div
        className={`max-w-[75%] relative flex flex-col gap-1 ${isUser ? "items-end" : "items-start"}`}
      >
        <div
          className={`px-4 py-3 rounded-2xl text-[13px] leading-relaxed ${
            isUser
              ? "bg-primary text-white rounded-br-sm shadow-lg shadow-primary/25"
              : "bg-card border border-border/60 text-foreground rounded-bl-sm shadow-sm"
          }`}
        >
          {msg.streaming ? (
            <span>
              {renderMarkdown(msg.content)}
              <span className="inline-block w-0.5 h-3.5 bg-primary ml-0.5 animate-pulse align-middle" />
            </span>
          ) : (
            renderMarkdown(msg.content)
          )}
        </div>
        <div className={`flex items-center gap-2 px-1 ${isUser ? "flex-row-reverse" : ""}`}>
          <span className="text-[10px] text-text-dim">{msg.time}</span>
          {!isUser && !msg.streaming && (
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
  const [messages, setMessages] = useState(() => [
    {
      id: 1,
      role: "assistant",
      content:
        "Bonjour ! Je suis **FinMAG Copilot**, votre assistant financier connecte au data warehouse MAG Distribution.\n\nJ'analyse vos **donnees en temps reel** - CA, tresorerie, stocks, clients, fiscalite - et je vous fournis des recommandations actionnables.\n\nQue souhaitez-vous explorer ?",
      time: new Date().toLocaleTimeString("fr-TN", { hour: "2-digit", minute: "2-digit" }),
      streaming: false,
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

  const sendMessage = async (text) => {
    const content = (text || input).trim();
    if (!content || isStreaming) return;

    const now = () =>
      new Date().toLocaleTimeString("fr-TN", { hour: "2-digit", minute: "2-digit" });

    const userMsg = { id: Date.now(), role: "user", content, time: now(), streaming: false };

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
      { id: assistantId, role: "assistant", content: "", time: now(), streaming: true },
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
        prev.map((m) => (m.id === assistantId ? { ...m, streaming: false, time: now() } : m)),
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
    if (abortRef.current) abortRef.current.abort();
    const now = new Date().toLocaleTimeString("fr-TN", { hour: "2-digit", minute: "2-digit" });
    setMessages([
      {
        id: Date.now(),
        role: "assistant",
        content: "Conversation reinitialisee. Comment puis-je vous aider ?",
        time: now,
        streaming: false,
      },
    ]);
    setIsStreaming(false);
  };

  const showSuggestions = messages.length <= 1 && !isStreaming;

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] max-w-4xl mx-auto">
      <div className="flex items-center justify-between mb-4 flex-shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-primary/60 flex items-center justify-center shadow-lg shadow-primary/30">
            <Sparkles size={18} className="text-white" />
          </div>
          <div>
            <h1 className="text-[18px] font-bold text-foreground leading-none">Copilote Décisionnel</h1>
            <div className="flex items-center gap-1.5 mt-0.5">
              {llmStatus.llm_ready === null ? (
                <span className="text-[11px] text-text-dim">Connexion...</span>
              ) : llmStatus.llm_ready ? (
                <>
                  <span className="w-1.5 h-1.5 rounded-full bg-green-400 animate-pulse" />
                  <span className="text-[11px] text-text-dim flex items-center gap-1">
                    <Cpu size={10} className="text-primary" />
                    {llmStatus.model || "Gemini 1.5 Flash"} - donnees live MAG
                  </span>
                </>
              ) : (
                <>
                  <AlertCircle size={11} className="text-amber-400" />
                  <span className="text-[11px] text-amber-400">
                    Cle API manquante - voir etl/.env
                  </span>
                </>
              )}
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

      <div className="flex-1 overflow-y-auto space-y-4 pr-1 pb-4">
        {messages.map((msg) => (
          <MessageBubble key={msg.id} msg={msg} />
        ))}
        {isStreaming && messages[messages.length - 1]?.role !== "assistant" && <TypingIndicator />}
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
                  disabled={isStreaming}
                  className="flex items-start gap-2.5 p-3 rounded-xl border border-border/60 bg-card hover:border-primary/40 hover:bg-primary/5 text-left transition-all duration-200 group disabled:opacity-50"
                >
                  <div className="w-7 h-7 rounded-lg bg-primary/10 flex items-center justify-center flex-shrink-0 group-hover:bg-primary/20 transition-colors">
                    <s.icon size={13} className="text-primary" />
                  </div>
                  <div className="min-w-0">
                    <p className="text-[12px] font-semibold text-foreground leading-none mb-1">
                      {s.label}
                    </p>
                    <p className="text-[11px] text-text-dim leading-relaxed line-clamp-2">
                      {s.text}
                    </p>
                  </div>
                  <ChevronRight
                    size={12}
                    className="text-text-dim flex-shrink-0 mt-1 opacity-0 group-hover:opacity-100 transition-opacity ml-auto"
                  />
                </button>
              ))}
            </div>
          </div>
        )}
      </div>

      <div className="flex-shrink-0 mt-2">
        <div className="flex gap-2 p-2 bg-card border border-border/60 rounded-2xl shadow-lg">
          <textarea
            ref={inputRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={
              isStreaming
                ? "FinMAG Copilot analyse vos données..."
                : "Posez votre question sur les donnees MAG Distribution..."
            }
            rows={1}
            disabled={isStreaming}
            className="flex-1 bg-transparent text-[13px] text-foreground placeholder:text-text-dim outline-none resize-none px-2 py-1.5 leading-relaxed max-h-32 disabled:opacity-60"
            style={{ minHeight: "36px" }}
            onInput={(e) => {
              e.target.style.height = "auto";
              e.target.style.height = Math.min(e.target.scrollHeight, 128) + "px";
            }}
          />
          <button
            onClick={() => sendMessage()}
            disabled={!input.trim() || isStreaming}
            className="w-9 h-9 rounded-xl bg-primary flex items-center justify-center flex-shrink-0 self-end shadow-md shadow-primary/30 hover:bg-primary/90 disabled:opacity-40 disabled:cursor-not-allowed transition-all duration-200 hover:scale-105 active:scale-95"
          >
            <Send size={15} className="text-white" />
          </button>
        </div>
        <p className="text-[10px] text-text-dim text-center mt-1.5">
          Entree pour envoyer - Maj+Entree pour nouvelle ligne - Reponses basees sur vos donnees
          live
        </p>
      </div>
    </div>
  );
}
