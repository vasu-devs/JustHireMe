// Settings modal
const Settings = ({ open, onClose, ghost, setGhost }) => {
  if (!open) return null;
  return (
    <>
      <div className="drawer-backdrop" onClick={onClose}/>
      <div style={{
        position: "fixed", top: "50%", left: "50%",
        transform: "translate(-50%, -50%)",
        width: "min(640px, 92vw)", maxHeight: "88vh",
        background: "var(--paper)", border: "1px solid var(--line)",
        borderRadius: 20, boxShadow: "var(--shadow-lg)",
        zIndex: 50, overflow: "hidden", display: "flex", flexDirection: "column",
        animation: "slide-up .3s ease",
      }}>
        <div className="row" style={{ padding: "18px 22px", borderBottom: "1px solid var(--line)", justifyContent: "space-between", background: "var(--blue-soft)" }}>
          <div className="col gap-1">
            <span className="eyebrow">Configuration</span>
            <h2 style={{ fontSize: 26 }}>Settings</h2>
          </div>
          <button className="btn btn-icon" onClick={onClose}><Icon name="x" size={15}/></button>
        </div>
        <div className="scroll" style={{ padding: 22, display: "flex", flexDirection: "column", gap: 14 }}>
          <Field tone="purple" icon="key" label="Anthropic API key" hint="Used by evaluator + tailor agents" type="password" placeholder="sk-ant-•••••••••••••" defaultValue=""/>
          <Field tone="orange" icon="key" label="OpenAI API key" hint="Fallback for embeddings" type="password" placeholder="sk-•••••••••••••" defaultValue=""/>
          <Field tone="blue" icon="link" label="LinkedIn session cookie" hint="Required for LinkedIn scraper" type="password" placeholder="li_at=•••" defaultValue=""/>
          <Field tone="green" icon="globe" label="Target job boards" hint="One URL per line" type="textarea" defaultValue={"https://lever.co/linear\nhttps://greenhouse.io/stripe\nhttps://ashby.hq/figma\nhttps://jobs.ashbyhq.com/anthropic"}/>

          <div style={{
            padding: 16, borderRadius: 14,
            background: ghost ? "var(--purple-soft)" : "var(--paper-2)",
            border: `1px solid ${ghost ? "var(--purple-ink)" : "var(--line)"}`,
            transition: "all .2s ease",
          }}>
            <div className="row" style={{ justifyContent: "space-between", alignItems: "center", gap: 12 }}>
              <div className="col gap-1" style={{ flex: 1 }}>
                <div className="row gap-2">
                  <Icon name="ghost" size={14} color={ghost ? "var(--purple-ink)" : "var(--ink-3)"}/>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>Ghost mode</div>
                  <span className="pill mono" style={{ background: ghost ? "var(--purple)" : "var(--paper-3)", color: ghost ? "var(--purple-ink)" : "var(--ink-3)", fontSize: 9.5, letterSpacing: "0.1em", textTransform: "uppercase" }}>{ghost ? "autonomous" : "manual"}</span>
                </div>
                <div style={{ fontSize: 12.5, color: "var(--ink-3)" }}>
                  {ghost ? "Agent applies automatically when match score > 0.85." : "Agent waits for your approval before submitting any application."}
                </div>
              </div>
              <button onClick={() => setGhost(!ghost)} style={{
                width: 46, height: 26, borderRadius: 999,
                background: ghost ? "var(--purple-ink)" : "var(--ink-4)",
                border: "none", cursor: "pointer", padding: 0,
                position: "relative", transition: "background .2s ease",
              }}>
                <span style={{
                  position: "absolute", top: 3, left: ghost ? 23 : 3,
                  width: 20, height: 20, borderRadius: "50%",
                  background: "white", transition: "left .2s ease",
                  boxShadow: "0 1px 3px rgba(0,0,0,0.2)",
                }}/>
              </button>
            </div>
          </div>
        </div>
        <div className="row" style={{ padding: "14px 22px", borderTop: "1px solid var(--line)", justifyContent: "flex-end", gap: 8, background: "var(--paper-2)" }}>
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={onClose}><Icon name="check" size={13}/> Save changes</button>
        </div>
      </div>
    </>
  );
};

const Field = ({ tone, icon, label, hint, type = "text", placeholder, defaultValue }) => (
  <div style={{
    padding: 14, borderRadius: 12,
    background: `var(--${tone}-soft)`,
    border: `1px solid var(--${tone})`,
  }}>
    <div className="row gap-2" style={{ marginBottom: 8 }}>
      <div style={{ width: 22, height: 22, borderRadius: 6, background: `var(--${tone})`, color: `var(--${tone}-ink)`, display: "grid", placeItems: "center" }}>
        <Icon name={icon} size={12}/>
      </div>
      <div style={{ fontSize: 13, fontWeight: 600 }}>{label}</div>
      <div style={{ fontSize: 11.5, color: "var(--ink-3)", marginLeft: 4 }}>{hint}</div>
    </div>
    {type === "textarea" ? (
      <textarea defaultValue={defaultValue} rows={4} className="mono" style={{
        width: "100%", padding: "10px 12px", borderRadius: 9,
        border: "1px solid var(--line)", background: "var(--card)",
        fontSize: 12, resize: "vertical",
      }}/>
    ) : (
      <input type={type} placeholder={placeholder} defaultValue={defaultValue} className="mono" style={{
        width: "100%", padding: "10px 12px", borderRadius: 9,
        border: "1px solid var(--line)", background: "var(--card)",
        fontSize: 12,
      }}/>
    )}
  </div>
);

window.Settings = Settings;
