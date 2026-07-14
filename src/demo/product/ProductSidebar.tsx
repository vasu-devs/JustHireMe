import { DemoIcon } from "../DemoIcon";
import type { ProductView } from "../DemoApp";

const items: Array<{ label: ProductView; icon: string; hint: string; tone: string; badge?: string }> = [
  { label: "Overview", icon: "overview", hint: "Home board", tone: "peach" },
  { label: "Pipeline", icon: "inbox", hint: "Application flow", tone: "blue", badge: "12" },
  { label: "Scout", icon: "radar", hint: "Search map", tone: "mint", badge: "3" },
  { label: "Tailor", icon: "tailor", hint: "Asset workshop", tone: "pink" },
  { label: "Profile", icon: "profile", hint: "Evidence map", tone: "lilac" },
];

export function ProductSidebar({ view, onChange, open, onClose }: { view: ProductView; onChange: (value: ProductView) => void; open: boolean; onClose: () => void }) {
  return <aside className={`product-sidebar ${open ? "open" : ""}`}>
    <div className="product-logo"><span>J</span><div className="product-wordmark"><strong>JustHireMe</strong><small>search workspace</small></div><i>private</i><button onClick={onClose} aria-label="Close navigation"><DemoIcon name="close" /></button></div>
    <div className="product-space"><span className="product-avatar">VS</span><div><small>Active vision board</small><strong>Vasudev’s search</strong><em>July sprint · Week 29</em></div><DemoIcon name="chevron" /></div>
    <nav aria-label="Product navigation">
      <p><span>Workspace</span><i>5 rooms</i></p>
      {items.map(item => <button key={item.label} className={view === item.label ? "active" : ""} onClick={() => { onChange(item.label); onClose(); }}><span className={`nav-stamp ${item.tone}`}><DemoIcon name={item.icon} /></span><span className="nav-copy"><strong>{item.label}</strong><small>{item.hint}</small></span>{item.badge && <b>{item.badge}</b>}</button>)}
    </nav>
    <div className="product-sidebar-spacer" />
    <div className="sidebar-brief"><span>Pinned insight</span><strong>Three roles cleared your evidence bar.</strong><button onClick={() => { onChange("Overview"); onClose(); }}>Open shortlist <DemoIcon name="arrow" /></button></div>
    <div className="product-health"><div className="product-health-ring"><i /><i /><span>96</span></div><div><strong>Profile signal</strong><small>Excellent coverage</small></div></div>
    <button className="product-settings"><DemoIcon name="settings" /><span>Settings</span><kbd>⌘,</kbd></button>
    <div className="product-local"><span /><p><strong>Local engine</strong><small>All systems nominal</small></p></div>
  </aside>;
}
