import { DemoIcon } from "../DemoIcon";
import type { ProductView } from "../DemoApp";

const items: Array<{ label: ProductView; icon: string; badge?: string }> = [
  { label: "Overview", icon: "overview" },
  { label: "Pipeline", icon: "inbox", badge: "12" },
  { label: "Scout", icon: "radar", badge: "3" },
  { label: "Tailor", icon: "tailor" },
  { label: "Profile", icon: "profile" },
];

export function ProductSidebar({ view, onChange, open, onClose }: { view: ProductView; onChange: (value: ProductView) => void; open: boolean; onClose: () => void }) {
  return <aside className={`product-sidebar ${open ? "open" : ""}`}>
    <div className="product-logo"><span>J</span><strong>JustHireMe</strong><i>studio</i><button onClick={onClose} aria-label="Close navigation"><DemoIcon name="close" /></button></div>
    <div className="product-space"><span className="product-avatar">VS</span><div><strong>Vasudev's search</strong><small>Private workspace</small></div><DemoIcon name="chevron" /></div>
    <nav aria-label="Product navigation">
      <p>Workspace</p>
      {items.map(item => <button key={item.label} className={view === item.label ? "active" : ""} onClick={() => { onChange(item.label); onClose(); }}><DemoIcon name={item.icon} /><span>{item.label}</span>{item.badge && <b>{item.badge}</b>}</button>)}
    </nav>
    <div className="product-sidebar-spacer" />
    <div className="product-health"><div className="product-health-ring"><i /><i /><span>96</span></div><div><strong>Profile signal</strong><small>Excellent coverage</small></div></div>
    <button className="product-settings"><DemoIcon name="settings" /><span>Settings</span><kbd>⌘,</kbd></button>
    <div className="product-local"><span /><p><strong>Local engine</strong><small>All systems nominal</small></p></div>
  </aside>;
}
