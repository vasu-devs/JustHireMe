import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { DemoIcon } from "../../demo/DemoIcon";
import type { ApiFetch, GraphStats, View } from "../../types";
import { applyProfileDeleteMarkers, entryTitle, mergeProfileWithGraphFallback, normalizeProfileResponse, profileDeleteKey, profileDeletePath, profileHasDeleteMarker, removeProfileItem } from "./profileUtils";
import type { ProfileDeleteMarker } from "./profileUtils";

type ProfileData = ReturnType<typeof normalizeProfileResponse>;

const recordOf = (item: unknown): Record<string, unknown> =>
  item && typeof item === "object" && !Array.isArray(item) ? item as Record<string, unknown> : {};

const textOf = (value: unknown) => typeof value === "string" || typeof value === "number" ? String(value) : "";

function entryDetail(item: unknown, keys: string[]) {
  const row = recordOf(item);
  return keys.map(key => textOf(row[key])).filter(Boolean).join(" · ");
}

function initials(name: string) {
  const value = name.trim() || "Your Profile";
  return value.split(/\s+/).slice(0, 2).map(part => part[0]).join("").toUpperCase();
}

// Per-item deletion, restored after the dossier redesign dropped it. Extracted
// so the confirm/single-flight/DELETE contract stays testable without a DOM
// renderer. The single-flight guard is load-bearing: concurrent DELETEs from
// rapid clicks contend on the backend graph lock, so extras are dropped.
export function createProfileItemDelete({ api, isBusy, setBusy, reload, setError, onDeleted }: {
  api: ApiFetch;
  isBusy: () => boolean;
  setBusy: (marker: string | null) => void;
  reload: () => Promise<void>;
  setError: (message: string | null) => void;
  onDeleted?: (type: string, key: string) => void;
}) {
  return async (type: string, item: unknown) => {
    if (isBusy()) return;
    if (!window.confirm(`Remove "${entryTitle(item) || "this entry"}" from your profile?`)) return;
    const key = profileDeleteKey(item);
    setBusy(`${type}:${key}`);
    try {
      const response = await api(profileDeletePath(type, key), { method: "DELETE" });
      if (!response.ok) throw new Error(`Delete failed (${response.status})`);
      onDeleted?.(type, key);
      await reload();
      window.dispatchEvent(new CustomEvent("graph-refresh"));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Delete failed");
    } finally {
      setBusy(null);
    }
  };
}

export function ProfileView({ api, setView, stats }: { api: ApiFetch; setView: (view: View) => void; stats?: GraphStats }) {
  const [profile, setProfile] = useState<ProfileData>(() => normalizeProfileResponse(mergeProfileWithGraphFallback({}, stats)));
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);
  // Ref, not state: the guard must reject a second click in the same tick.
  const deleteFlightRef = useRef(false);
  // Deleted items must not resurrect from the STALE graph-stats prop during
  // the window between a successful DELETE and the debounced graph refetch —
  // markers suppress them in every merge until the stats prop catches up.
  const deleteMarkersRef = useRef<ProfileDeleteMarker[]>([]);

  const load = useCallback(async () => {
    setRefreshing(true);
    try {
      const response = await api("/api/v1/profile");
      if (!response.ok) throw new Error(`Profile load failed (${response.status})`);
      const body = await response.json();
      // Drop markers the stats prop no longer resurrects; apply the rest.
      deleteMarkersRef.current = deleteMarkersRef.current.filter(marker =>
        profileHasDeleteMarker(mergeProfileWithGraphFallback({}, stats), marker));
      setProfile(normalizeProfileResponse(applyProfileDeleteMarkers(
        mergeProfileWithGraphFallback(body, stats), deleteMarkersRef.current)));
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "Profile load failed");
    } finally {
      setRefreshing(false);
    }
  }, [api, stats]);

  const deleteItem = useMemo(() => createProfileItemDelete({
    api,
    isBusy: () => deleteFlightRef.current,
    setBusy: marker => { deleteFlightRef.current = marker !== null; setDeleting(marker); },
    reload: load,
    setError,
    onDeleted: (type, key) => {
      deleteMarkersRef.current = [...deleteMarkersRef.current, { type, id: key }];
      setProfile(prev => removeProfileItem(prev, type, key));
    },
  }), [api, load]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    const refresh = () => { void load(); };
    window.addEventListener("profile-refresh", refresh);
    return () => window.removeEventListener("profile-refresh", refresh);
  }, [load]);

  const evidenceCount = profile.skills.length + profile.projects.length + profile.exp.length + profile.education.length + profile.certifications.length + profile.achievements.length;
  const readiness = Math.min(98, Math.max(38, 48 + Math.min(50, evidenceCount * 3)));
  const roleClarity = Math.min(96, 58 + Math.min(38, profile.exp.length * 8 + profile.projects.length * 4));
  const recency = Math.min(95, 64 + Math.min(31, profile.projects.length * 6 + profile.achievements.length * 3));
  const name = profile.n || "Build your professional profile";
  const latestRole = profile.exp[0] ? entryTitle(profile.exp[0]) : "Your evidence-backed career story";
  const contacts = [profile.identity.city, profile.identity.email, profile.identity.linkedin_url ? "LinkedIn connected" : ""].filter(Boolean);
  const skills = profile.skills.slice(0, 12);
  const projects = profile.projects.slice(0, 4);
  const experience = profile.exp.slice(0, 4);
  const credentialGroups = [
    { type: "education", label: "Education", items: profile.education },
    { type: "certification", label: "Certifications", items: profile.certifications },
    { type: "achievement", label: "Achievements", items: profile.achievements },
  ].filter(group => group.items.length);
  const credentialCount = profile.education.length + profile.certifications.length + profile.achievements.length;

  return <div className="profile-view product-enter production-profile-exact profile-dossier scroll">
    <div className="view-toolbar profile-dossier-toolbar">
      <div><span className="product-eyebrow">Your professional identity</span><h2>Profile dossier</h2><span className="toolbar-scribble">specific proof, clearly told ✦</span></div>
      <div className="view-toolbar-actions">
        <button onClick={() => setView("graph")}><DemoIcon name="graph" />Open evidence atlas</button>
        <button className="toolbar-primary" onClick={() => setView("ingestion")}><DemoIcon name="plus" />Add evidence</button>
      </div>
    </div>

    {error && <div className="pipeline-notice error"><DemoIcon name="close" /><span>{error}</span></div>}

    <section className="profile-identity-card">
      <div className="profile-avatar" aria-hidden="true">{initials(profile.n)}</div>
      <div className="profile-identity-copy">
        <span className="profile-kicker">Candidate profile · locally private</span>
        <h3>{name}</h3>
        <strong>{latestRole}</strong>
        <p>{profile.s || "Turn your projects, skills, and outcomes into a profile Scout can actually use for specific applications."}</p>
        <div className="profile-contact-row">
          {contacts.length ? contacts.map(item => <span key={item}><i />{item}</span>) : <span><i />Add location and contact details</span>}
        </div>
      </div>
      <div className="profile-readiness-seal">
        <span>Application readiness</span><strong>{readiness}</strong><small>out of 100</small>
        <button onClick={() => { window.dispatchEvent(new CustomEvent("graph-refresh")); void load(); }} disabled={refreshing}>{refreshing ? "Refreshing…" : "Recheck profile"}</button>
      </div>
    </section>

    <section className="profile-metric-row" aria-label="Profile coverage">
      <article><span>01</span><strong>{profile.skills.length}</strong><p>Verified skills</p><small>Used to rank role overlap</small></article>
      <article><span>02</span><strong>{profile.projects.length}</strong><p>Shipped projects</p><small>Your strongest proof</small></article>
      <article><span>03</span><strong>{profile.exp.length}</strong><p>Career chapters</p><small>Context for seniority</small></article>
      <article><span>04</span><strong>{profile.achievements.length + profile.certifications.length}</strong><p>Credibility markers</p><small>Outcomes and credentials</small></article>
    </section>

    <div className="profile-dossier-grid">
      <main className="profile-evidence-column">
        <section className="profile-dossier-section profile-skills-section">
          <header><div><span className="product-eyebrow">Capability index</span><h3>Skills Scout can defend</h3></div><button onClick={() => setView("ingestion")}>Edit skills <DemoIcon name="arrow" /></button></header>
          <div className="profile-skill-cloud">
            {skills.length ? skills.map((item, index) => <span key={`${entryTitle(item)}-${index}`}><i>{String(index + 1).padStart(2, "0")}</i>{entryTitle(item)}<button className="profile-chip-delete" onClick={() => void deleteItem("skill", item)} disabled={deleting !== null} aria-label={`Remove skill ${entryTitle(item)}`}><DemoIcon name="close" /></button></span>) : <button onClick={() => setView("ingestion")}><DemoIcon name="plus" />Add your first verified skill</button>}
          </div>
        </section>

        <section className="profile-dossier-section">
          <header><div><span className="product-eyebrow">Proof of work</span><h3>Projects worth leading with</h3></div><button onClick={() => setView("ingestion")}>Manage projects <DemoIcon name="arrow" /></button></header>
          <div className="profile-project-list">
            {projects.length ? projects.map((item, index) => <article key={`${entryTitle(item)}-${index}`}>
              <span className="profile-entry-index">{String(index + 1).padStart(2, "0")}</span>
              <div><h4>{entryTitle(item)}</h4><p>{entryDetail(item, ["impact", "description", "d"]) || "Add the outcome, scale, or decision that made this work matter."}</p><small>{entryDetail(item, ["stack", "repo"]) || "Project evidence"}</small></div>
              <button className="profile-entry-delete" onClick={() => void deleteItem("project", item)} disabled={deleting !== null} aria-label={`Remove ${entryTitle(item)}`}><DemoIcon name="close" /></button>
              <button onClick={() => setView("ingestion")} aria-label={`Edit ${entryTitle(item)}`}><DemoIcon name="chevron" /></button>
            </article>) : <ProfileEmpty title="No projects connected yet" body="Add one shipped project with a concrete outcome." onClick={() => setView("ingestion")} />}
          </div>
        </section>

        <section className="profile-dossier-section">
          <header><div><span className="product-eyebrow">Career timeline</span><h3>Experience with context</h3></div><button onClick={() => setView("ingestion")}>Edit timeline <DemoIcon name="arrow" /></button></header>
          <div className="profile-timeline">
            {experience.length ? experience.map((item, index) => <article key={`${entryTitle(item)}-${index}`}><i /><div><span>{entryDetail(item, ["period"]) || `Chapter ${String(index + 1).padStart(2, "0")}`}</span><h4>{entryTitle(item)}</h4><strong>{entryDetail(item, ["co", "company"])}</strong><p>{entryDetail(item, ["d", "description"]) || "Add the scope and outcome so generated applications stay grounded."}</p><button className="profile-entry-delete" onClick={() => void deleteItem("experience", item)} disabled={deleting !== null} aria-label={`Remove ${entryTitle(item)}`}><DemoIcon name="close" /></button></div></article>) : <ProfileEmpty title="Your timeline is empty" body="Add a role, freelance chapter, or meaningful apprenticeship." onClick={() => setView("ingestion")} />}
          </div>
        </section>
      </main>

      <aside className="profile-insight-column">
        <section className="profile-insight-card">
          <span className="product-eyebrow">Signal quality</span><h3>{readiness >= 85 ? "Strong and specific" : readiness >= 65 ? "Useful, with room to sharpen" : "Needs more evidence"}</h3>
          <p>These scores reflect how confidently Scout can turn your information into truthful, role-specific material.</p>
          <div className="profile-bars">
            <label><span>Evidence depth <b>{readiness}</b></span><i><em style={{ width: `${readiness}%` }} /></i></label>
            <label><span>Role clarity <b>{roleClarity}</b></span><i><em style={{ width: `${roleClarity}%` }} /></i></label>
            <label><span>Evidence recency <b>{recency}</b></span><i><em style={{ width: `${recency}%` }} /></i></label>
          </div>
        </section>

        <section className="profile-next-card">
          <span className="profile-note-tape" />
          <span className="product-eyebrow">Best next move</span>
          <h3>{profile.projects.length ? "Add measurable impact" : "Connect one shipped project"}</h3>
          <p>{profile.projects.length ? "Choose a project and record the result: users, revenue, latency, reliability, or time saved." : "One concrete project gives Scout far more signal than another generic skill list."}</p>
          <button onClick={() => setView("ingestion")}>Improve my evidence <DemoIcon name="arrow" /></button>
        </section>

        <section className="profile-coverage-card">
          <header><span className="product-eyebrow">Connected sources</span><strong>{evidenceCount}</strong></header>
          <button onClick={() => setView("ingestion")}><DemoIcon name="file" /><span><strong>Resume and identity</strong><small>{profile.n ? "Connected" : "Needs attention"}</small></span><DemoIcon name="chevron" /></button>
          <button onClick={() => setView("ingestion")}><DemoIcon name="overview" /><span><strong>Projects and outcomes</strong><small>{profile.projects.length} entries</small></span><DemoIcon name="chevron" /></button>
          <button onClick={() => setView("graph")}><DemoIcon name="graph" /><span><strong>Evidence relationships</strong><small>{Number(stats?.graph?.edges?.length || evidenceCount)} live links</small></span><DemoIcon name="chevron" /></button>
        </section>

        <section className="profile-credentials-card">
          <header><span className="product-eyebrow">Credibility markers</span><strong>{credentialCount}</strong></header>
          {credentialGroups.length ? credentialGroups.map(group => <div className="profile-credential-group" key={group.type}>
            <span>{group.label}</span>
            <div>{group.items.map((item, index) => <span className="profile-credential-chip" key={`${entryTitle(item)}-${index}`}>{entryTitle(item)}<button className="profile-chip-delete" onClick={() => void deleteItem(group.type, item)} disabled={deleting !== null} aria-label={`Remove ${group.type} ${entryTitle(item)}`}><DemoIcon name="close" /></button></span>)}</div>
          </div>) : <p className="profile-credentials-empty">Degrees, certifications, and awards land here once ingested.</p>}
        </section>
      </aside>
    </div>
  </div>;
}

function ProfileEmpty({ title, body, onClick }: { title: string; body: string; onClick: () => void }) {
  return <button className="profile-empty-state" onClick={onClick}><DemoIcon name="plus" /><span><strong>{title}</strong><small>{body}</small></span></button>;
}
