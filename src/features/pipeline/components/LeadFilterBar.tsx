import type { ReactNode } from "react";
import Icon from "../../../shared/components/Icon";
import type { LeadSort, SeniorityFilter } from "../../../types";

export function LeadFilterBar({
  search, setSearch, platform, setPlatform, sort, setSort,
  seniority, setSeniority, platforms, total, shown, label, actions,
}: {
  search: string; setSearch: (v: string) => void;
  platform: string; setPlatform: (v: string) => void;
  sort: LeadSort; setSort: (v: LeadSort) => void;
  seniority: SeniorityFilter; setSeniority: (v: SeniorityFilter) => void;
  platforms: string[]; total: number; shown: number; label: string;
  actions?: ReactNode;
}) {
  const hasFilters = Boolean(search || platform || seniority !== "all" || sort !== "recommended");
  const resetFilters = () => {
    setSearch("");
    setPlatform("");
    setSeniority("all");
    setSort("recommended");
  };

  return (
    <div className="pipeline-filterbar">
      <label className="pipeline-searchbox">
        <Icon name="search" size={14} />
        <input
          value={search}
          onChange={e => setSearch(e.target.value)}
          placeholder={`Search ${label}`}
        />
      </label>

      <div className="pipeline-filter-fields">
        <label className="pipeline-field">
          <span>Source</span>
          <select value={platform} onChange={e => setPlatform(e.target.value)}>
            <option value="">All sources</option>
            {platforms.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <label className="pipeline-field">
          <span>Level</span>
          <select value={seniority} onChange={e => setSeniority(e.target.value as SeniorityFilter)}>
            <option value="all">All levels</option>
            <option value="beginner">Beginner</option>
            <option value="fresher">Fresher</option>
            <option value="junior">Junior</option>
            <option value="mid">Mid</option>
            <option value="senior">Senior</option>
            <option value="unknown">Unknown</option>
          </select>
        </label>
        <label className="pipeline-field">
          <span>Sort</span>
          <select value={sort} onChange={e => setSort(e.target.value as LeadSort)}>
            <option value="recommended">Recommended</option>
            <option value="newest">Newest</option>
            <option value="signal">Best signal</option>
            <option value="match">Best match</option>
            <option value="company">Company</option>
          </select>
        </label>
      </div>

      <div className="pipeline-filter-actions">
        <span className="pipeline-count mono">{shown}/{total}</span>
        {hasFilters && <button className="pipeline-clear" onClick={resetFilters}>Clear</button>}
      </div>
      {actions && <div className="pipeline-actions">{actions}</div>}
    </div>
  );
}
