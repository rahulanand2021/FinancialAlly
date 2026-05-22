"use client";

import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { usePortfolio } from "@/hooks/PortfolioContext";
import { ChatAction, ChatMessage } from "@/types/api";
import { formatQuantity } from "@/lib/format";
import Panel from "./Panel";

interface DisplayMessage extends ChatMessage {
  pending?: boolean;
}

function chipForAction(a: ChatAction): { text: string; tone: "good" | "bad" | "info" } {
  if (a.status === "error") {
    return { text: a.error ?? `${a.ticker} failed`, tone: "bad" };
  }
  if (a.type === "trade" && a.side && a.quantity !== undefined) {
    const verb = a.side === "buy" ? "Bought" : "Sold";
    return {
      text: `${verb} ${formatQuantity(a.quantity)} ${a.ticker}`,
      tone: a.side === "buy" ? "good" : "info",
    };
  }
  if (a.type === "watchlist") {
    return { text: `${a.action === "add" ? "+" : "-"}${a.ticker}`, tone: "info" };
  }
  return { text: a.ticker, tone: "info" };
}

function ActionChips({ actions }: { actions?: ChatAction[] | null }) {
  if (!actions || actions.length === 0) return null;
  const items = actions.map(chipForAction);

  return (
    <div className="flex flex-wrap gap-1 mt-1">
      {items.map((c, i) => {
        const cls =
          c.tone === "good"
            ? "bg-up/15 text-up border-up/30"
            : c.tone === "bad"
              ? "bg-down/15 text-down border-down/30"
              : "bg-accent-blue/15 text-accent-blue border-accent-blue/30";
        return (
          <span
            key={i}
            data-testid="chat-action-chip"
            className={`text-[10px] font-mono px-1.5 py-0.5 border rounded ${cls}`}
          >
            {c.text}
          </span>
        );
      })}
    </div>
  );
}

export default function ChatPanel() {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const { refresh } = usePortfolio();

  useEffect(() => {
    const el = scrollRef.current;
    if (el && typeof el.scrollTo === "function") {
      el.scrollTo({ top: el.scrollHeight });
    } else if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  const send = async () => {
    const content = input.trim();
    if (!content || sending) return;
    const userMsg: DisplayMessage = { role: "user", content };
    setMessages((prev) => [
      ...prev,
      userMsg,
      { role: "assistant", content: "", pending: true },
    ]);
    setInput("");
    setSending(true);
    try {
      const res = await api.sendChat(content);
      setMessages((prev) => {
        const next = prev.slice(0, -1);
        next.push({ role: "assistant", content: res.message, actions: res.actions });
        return next;
      });
      await refresh();
    } catch (e) {
      setMessages((prev) => {
        const next = prev.slice(0, -1);
        next.push({
          role: "assistant",
          content: `Error: ${(e as Error).message}`,
        });
        return next;
      });
    } finally {
      setSending(false);
    }
  };

  return (
    <Panel title="AI Assistant">
      <div className="flex flex-col h-full">
        <div
          ref={scrollRef}
          data-testid="chat-history"
          className="flex-1 overflow-auto p-2 space-y-2"
        >
          {messages.length === 0 && (
            <div className="text-xs text-text-muted p-2">
              Ask FinAlly about your portfolio, request analysis, or have it execute trades.
            </div>
          )}
          {messages.map((m, i) => (
            <div
              key={i}
              data-testid={`chat-message-${m.role}`}
              className={`text-sm rounded p-2 ${
                m.role === "user"
                  ? "bg-accent-blue/10 border border-accent-blue/30"
                  : "bg-bg-panel-hover border border-border-muted"
              }`}
            >
              {m.pending ? (
                <span className="text-text-muted text-xs italic">Thinking...</span>
              ) : (
                <>
                  <div className="whitespace-pre-wrap">{m.content}</div>
                  <ActionChips actions={m.actions} />
                </>
              )}
            </div>
          ))}
        </div>
        <form
          onSubmit={(e) => {
            e.preventDefault();
            void send();
          }}
          className="border-t border-border-muted p-2 flex gap-2"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask FinAlly..."
            disabled={sending}
            data-testid="chat-input"
            className="flex-1 px-2 py-1 text-sm bg-bg-base border border-border-muted rounded focus:outline-none focus:border-accent-blue disabled:opacity-50"
          />
          <button
            type="submit"
            disabled={sending || !input.trim()}
            data-testid="chat-send-button"
            className="px-3 py-1 text-sm font-semibold bg-accent-purple text-white rounded hover:bg-accent-purple/80 disabled:opacity-50"
          >
            Send
          </button>
        </form>
      </div>
    </Panel>
  );
}
