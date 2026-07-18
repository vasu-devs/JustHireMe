import { useMemo, useRef, useState } from "react";
import Icon from "./Icon";
import type { ApiFetch } from "../../types";

type Msg = { role: "user" | "assistant"; content: string };

const STARTER: Msg = {
  role: "assistant",
  content: "Ask me how to use JustHireMe, configure sources, generate packages, or understand a lead.",
};

export function HelpChat({ api }: { api: ApiFetch }) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([STARTER]);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const scroller = useRef<HTMLDivElement>(null);
  const canSend = Boolean(draft.trim()) && !busy;

  const subtitle = useMemo(() => busy ? "Thinking..." : "Project help", [busy]);

  const send = async () => {
    const question = draft.trim();
    if (!question || busy) return;
    const next: Msg[] = [...messages, { role: "user", content: question }];
    setMessages(next);
    setDraft("");
    setBusy(true);
    try {
      const r = await api("/api/v1/help/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question, history: next.slice(-8) }),
      });
      if (!r.ok) throw new Error(`Help returned ${r.status}`);
      const data = await r.json();
      setMessages([...next, { role: "assistant", content: data.answer || "I could not answer that yet." }]);
      window.setTimeout(() => scroller.current?.scrollTo({ top: scroller.current.scrollHeight, behavior: "smooth" }), 0);
    } catch (e) {
      setMessages([...next, { role: "assistant", content: e instanceof Error ? e.message : "Help chat failed." }]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="help-chat">
      {open && (
        <section className="help-chat-panel">
          <div className="help-chat-head">
            <div>
              <div className="eyebrow">JustHireMe Assistant</div>
              <div className="help-chat-title">{subtitle}</div>
            </div>
            <button className="btn btn-icon" onClick={() => setOpen(false)} aria-label="Close help">
              <Icon name="x" size={14} />
            </button>
          </div>
          <div className="help-chat-messages" ref={scroller}>
            {messages.map((m, i) => (
              <div key={i} className={`help-chat-msg ${m.role}`}>
                {m.content}
              </div>
            ))}
          </div>
          <div className="help-chat-input">
            <textarea
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onKeyDown={e => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send();
                }
              }}
              rows={2}
              placeholder="Ask how to scan, rank, customize, or configure..."
            />
            <button className="btn btn-accent btn-icon" onClick={send} disabled={!canSend} aria-label="Send help question">
              <Icon name="arrow-up" size={14} color="#fff" />
            </button>
          </div>
        </section>
      )}
      <button className="help-chat-fab" onClick={() => setOpen(v => !v)} aria-label="Open help chat">
        {/* currentColor so the theme CSS controls icon contrast (a hardcoded
            #fff was invisible on the cream fab in dark mode) */}
        <Icon name="spark" size={18} color="currentColor" />
      </button>
    </div>
  );
}
