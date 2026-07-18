import type { ReactNode } from "react";

export function ProductionViewIntro({
  index,
  eyebrow,
  title,
  accent,
  description,
  note,
  actions,
}: {
  index: string;
  eyebrow: string;
  title: string;
  accent: string;
  description: ReactNode;
  note?: ReactNode;
  actions?: ReactNode;
}) {
  return <header className="production-view-intro">
    <div className="production-view-index">{index}</div>
    <div className="production-view-copy">
      <span>{eyebrow}</span>
      <h1>{title} <em>{accent}</em></h1>
      <p>{description}</p>
    </div>
    {(note || actions) && <aside className="production-view-note">
      <span className="production-tape" />
      {note && <div>{note}</div>}
      {actions && <nav>{actions}</nav>}
    </aside>}
  </header>;
}
