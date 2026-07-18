import { useMemo, useState } from "react";
import type { LogLine } from "../../types";
import { ProductionViewIntro } from "../../shared/components/ProductionViewIntro";

type ActivityTab = "all" | "scout" | "eval" | "customize" | "system";

function visibleForTab(logs: LogLine[], tab: ActivityTab) {
  return logs.filter(line => {
    const message = line.msg.toLowerCase();
    if (tab === "all") return line.kind !== "heartbeat";
    if (tab === "scout") return line.src === "scout" || (line.kind === "agent" && message.includes("scout"));
    if (tab === "eval") return line.src === "eval" || (line.kind === "agent" && (message.includes("eval") || message.includes("scor")));
    if (tab === "customize") return line.src === "apply" || (line.kind === "agent" && (message.includes("custom") || message.includes("generat") || message.includes("package")));
    if (tab === "system") return line.kind === "system";
    return true;
  });
}

export function ActivityView({ logs }: { logs: LogLine[] }) {
  const [actTab, setActTab] = useState<ActivityTab>("all");
  const [copied, setCopied] = useState(false);
  const visibleLogs = useMemo(() => visibleForTab(logs, actTab), [actTab, logs]);

  const copyThinking = async () => {
    const body = visibleLogs.map(line => `[${line.ts}] ${line.kind.toUpperCase()} ${line.src}: ${line.msg}`).join("\n");
    const text = body || "No agent logs visible.";
    if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(text);
    else {
      const textarea = document.createElement("textarea");
      textarea.value = text;
      textarea.style.position = "fixed";
      textarea.style.opacity = "0";
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand("copy");
      document.body.removeChild(textarea);
    }
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1400);
  };

  return <div className="production-activity-page scroll">
    <ProductionViewIntro
      index="05"
      eyebrow="Scout’s field log"
      title="See what changed,"
      accent="not just what loaded."
      description={<>A readable record of discovery, evaluation, customization, and system decisions—straight from the live agent.</>}
      note={<><strong>{visibleLogs.length}</strong><span>visible notes</span><small><i /> listening now</small></>}
    />

    <section className="production-activity-ledger">
      <header>
        <div className="production-activity-tabs">{(["all", "scout", "eval", "customize", "system"] as const).map(tab => <button key={tab} className={actTab === tab ? "active" : ""} onClick={() => setActTab(tab)}>{tab === "eval" ? "Evaluation" : tab}</button>)}</div>
        <button className="btn" onClick={copyThinking}>{copied ? "Copied" : "Copy field notes"}</button>
      </header>
      <div className="production-log-paper scroll">
        {visibleLogs.length > 0 ? visibleLogs.map((line, index) => {
          const tone = line.kind === "heartbeat" ? "blue" : line.kind === "agent" ? "green" : "yellow";
          return <article key={line.id}>
            <span className="production-log-index">{String(index + 1).padStart(2, "0")}</span>
            <time>{line.ts}</time>
            <span className={`production-log-kind ${tone}`}>{line.kind}</span>
            <p><strong>{line.src}</strong><span>{line.msg}</span></p>
          </article>;
        }) : <div className="production-log-empty-state"><strong>No notes in this filter yet.</strong><p>Scout’s next matching event will land here automatically.</p></div>}
      </div>
      <footer><span><i /> live journal</span><p>Newest evidence is recorded as it happens.</p></footer>
    </section>
  </div>;
}
