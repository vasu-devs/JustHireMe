# JustHireMe — Candidate↔Job Fit Evaluation Algorithm (v2)
## The Coverage-Grounded Fit Engine (CGFE)

> **Status:** definitive engineering specification / design doc (not yet implemented).
> **Date:** 2026-07-20. **Author:** produced by a deep-research + adversarial-design pass
> (103-agent SOTA research → 4 independent architects → 3-judge adversarial panel → synthesis),
> grounded in a first-hand read of the entire current scoring stack.
> **Supersedes (once implemented):** the incumbent `score_job_lead` three-branch weighted engine,
> the `WRONG_FIELD_TERMS` blocklist, the `TECH_TAXONOMY`-only vocabulary, the provider-specific
> semantic stretch windows, the `min()` hard-cap ladder, and the binary 76 cliff.
>
> **Research provenance:** claims tagged `F1..F11` (verified findings) and `G1..G4` (honest gaps)
> refer to `docs/` research notes / the digest that seeded this design. Two are peer-reviewed
> (ConFit, RecSys 2024; Wilson & Caliskan resume-bias, AIES 2024); most architecture sources are
> recent (2026) arXiv preprints — treat exact numbers as directional, mechanisms as transferable.
>
> **Repo-fact corrections applied to the raw synthesis:** SQLite migrations live at
> `backend/data/sqlite/migrations/`; `001`–`004` already exist, so the new fit-columns migration is
> **`005_add_fit_columns.sql`** (not `002`). `scan_skills_in_text` lives in
> `backend/profile/normalization.py`.

**Scope:** this document specifies the **FIT axis** only — `score` ∈ [0,100], "how well does THIS
candidate fit THIS job." It never touches `signal_score` / `quality_score` (absolute posting
quality). The two axes are separate by hard rule (two-axis / PIVOT risk R2); feedback may move both,
on strictly separate channels (§10).

---

## 1. Design goals & the correctness principle

### 1.1 The one correctness principle
> **Candidate-relative, requirement-grounded, field-agnostic by construction.**
> Field membership is never enumerated. It is an *emergent, symmetric* outcome of how much of a job's
> requirements a candidate has real, graded evidence for, measured in a shared ESCO-grounded id space.
> The identical mechanism scores nurse↔nursing, welder↔welding, lawyer↔law, and dev↔software.
> "Wrong field" is the low-coverage + far-occupation corner, reached symmetrically with no profession list.

### 1.2 The decisive constraint that shaped every choice
The flagship path is **no-LLM + hash embeddings**, and in that mode `hash cosine ≈ token overlap`.
Therefore **cross-field detection and same-field coverage must rest on embedding-free signals** —
ESCO-id exact match + KG `RELATED_TO` graph hops + token/multilingual-altLabel Jaccard. Every
embedding-derived facet is confidence-down-weighted (κ) and surfaced when degraded, and can **never
drive a gate at full confidence in hash mode**. Any lead that is thin, non-English-unresolvable, or
uncertain routes to **REVIEW**, never silent-delete.

### 1.3 Non-negotiable invariants
1. **Field-agnostic by construction** — no profession blocklist, no tech-only taxonomy, no field-name
   code path, anywhere in the hot path.
2. **Keyless + deterministic-first is the flagship** — Stages A–F produce a fully calibrated score
   with no LLM and hash embeddings. LLM and ONNX are additive overlays that raise confidence, never gates.
3. **Two-axis separation** — this engine computes `score` (fit) only; `signal_score` is untouched and
   never folded in.
4. **Honest degradation is a math property, not a special case** — every degradation (hash mode,
   missing ONNX, missing leads column, LLM off, failed canonicalization, thin posting, non-English)
   sets a surfaced provenance flag and redistributes weight via confidence κ. No silent 15% noise
   channel; no fabricated logistics 95; `NEUTRAL ≠ 0`.
5. **Explainable** — every score ships `reason`, `match_points`, `gaps`, per-facet contributions,
   per-requirement `matched_via`, and every gate emits `{gate, value, reason}`.
6. **Cross-field detection is embedding-free-primary** — carried by ESCO-id coverage + graph-Jaccard
   occupation overlap; embedding cosine is corroboration only, at measured confidence.
7. **Legally-hard credentials gate multiplicatively and are non-buy-backable** — strong skill overlap
   cannot hand a high fit to a candidate lacking a required RN/CDL/bar/CPA.
8. **No unexplained constant** — every number is tagged `PRINCIPLED` (structural), `CALIBRATED`
   (fit on held-out data), or `SEED` (documented prior that a MAP-logistic fit washes out as golden
   data grows). See the Constants Register (§6.6).

---

## 2. Data-model changes required first (Phase 0 — ships alone, before any fusion change)

> *A perfect formula on corrupted inputs is still wrong.* These are the highest-ROI changes and they
> improve correctness with **zero fusion-math change**. Files are named exactly.

### 2.1 MUST-HAVE (block the whole redesign until landed)

| # | Change | Layer / file | Fixes (grounding) |
|---|---|---|---|
| M1 | **Key skills on ESCO concept id**, else a `casefold()`-only key with a symbol-preserving allowlist for `c++`,`c#`,`f#`,`.net`,`c` — never strip `+`/`#`. | `profile/normalization.py::normalize_skills` | C/C++/C# collapse |
| M2 | **Kill the tech-only `_valid_skill` gate.** Validity = "resolves to an ESCO concept **OR** is a multi-word noun phrase **OR** appears ≥2× as a stack/topic token." Recovers *phlebotomy, excel, figma, MIG welding.* | `profile/normalization.py::_valid_skill` | lowercase-skill rejection |
| M3 | **Negation / mention≠usage scan.** Drop matches inside `migrated away from / deprecated / no longer / instead of / no <X>` windows; require a usage verb or stack membership to credit. | `profile/normalization.py::scan_skills_in_text` | mention≠usage |
| M4 | **Unify parser caps** — one cap constant for heuristic and LLM parse paths (e.g. 200/80). Identical candidate → identical stored profile. | `profile/normalization.py`, ingest | cap asymmetry 40/8 vs 200/80 |
| M5 | **`leads` migration `005_add_fit_columns.sql`** — add `location, posted_date, tech_stack, salary_min, salary_max, remote, seniority_hint`; **persist them in the save path** (they exist on the in-flight dict, lost today). | `data/sqlite/migrations/005_add_fit_columns.sql` + lead save path | leads has no location/date/salary cols |

### 2.2 MUST-HAVE for facet fidelity (land in Phase 0/1; facets degrade to flagged NEUTRAL until then)

| # | Signal to recover | Layer / file | Facet unlocked |
|---|---|---|---|
| M6 | **Skill frequency** (the discarded `Counter`) → persist `skills[i].freq`. | snapshot builder | φ_proof `freq` |
| M7 | **Parse `period` → `{start,end,months}` once at ingest**; store `exp[i].months`; ambiguous → `months=null` + `date_confidence` flag (never guess). | `profile/ingest_store.py` | φ_sen, φ_proof recency |
| M8 | **Per-role `location` + per-role `skills`** persisted on the exp node + snapshot `exp[i].location`, `exp[i].s`. | Kuzu graph write + snapshot builder | φ_log, role-scoped evidence |
| M9 | **GitHub stars/forks/pushed_at** + portfolio per-project **`quality_score`** persisted on project node (currently computed for sort, then discarded). | `profile/ingest_store.py` + snapshot builder | φ_proof `ext` |
| M10 | **Snapshot merge = replace-by-source-version** (bump `snapshot_schema_version`) so a corrected résumé removes stale entries. | snapshot builder | data hygiene |

### 2.3 Nice-to-have (later phases)
- Skill-node `proficiency/recency/evidence_count/source` on Kuzu (stop the `cat→general` clobber).
- Degree level / field / institution / year parsed from opaque cert/education strings.

**Honesty rule:** until a signal in §2.2 lands, its facet emits `NEUTRAL` (dropped from fusion via
κ=0) plus a surfaced provenance flag (e.g. `evidence_thin`, `logistics_missing`,
`duration_estimated`). Missing never reads as bad.

---

## 3. End-to-end scoring pipeline

```
              ┌──────────── ONE-TIME / ON-PROFILE-CHANGE (cached on snapshot hash × mode) ───────────┐
              │ P0 ingest fixes (§2) → NEUTRALIZE identity (F10) → CANONICALIZE skills→ESCO ids (§5)  │
              │  → build CandidateCapabilitySet:                                                       │
              │     { esco_skill_ids(+evidence tier e), multi-occupation set O_c(+mass),               │
              │       graph-expanded skills (RELATED_TO ≤2 hop, decayed), section vectors[mode],       │
              │       parsed durations, freq/stars/recency/quality }                                   │
              └────────────────────────────────────────────────────────────────────────────────────────┘
                                            │ (per-scan, per DISCOVERED lead only)
 leads row {job_id,title,company,url,description}+opt{location,tech_stack,salary,remote,seniority}
        │
        ▼
 [A] PARSE + NEUTRALIZE JD → RequirementSet {phrases→ESCO ids, must/nice(refinement), req_years,
       is_licence flags, JD occupation O_j, logistics, thinness, extraction_confidence, lang}
        │
        ▼
 [B] FACETS (all ∈[0,1], each with confidence κ_f) — EMBEDDING-FREE PRIMARY, embedding = corroboration
        φ_cov  φ_proof  φ_occ        (keyless: ESCO-id + graph-Jaccard + multilingual-altLabel Jaccard)
        φ_sem  φ_log                 (φ_sem κ measured per mode → ~0 in hash; φ_log κ = data present)
        │
        ▼
 [C] PER-FACET CALIBRATION  f̃ = g_{f,mode}(raw)  (isotonic → percentile-of-quality, per embedding mode)
        │
        ▼
 [D] FUSION  q = Σ_f (κ_f·w_f)·f̃ / Σ_f (κ_f·w_f)     (w_f = priored MAP-logistic; confidence-weighted mean)
        │
        ▼
 [E] GATES (multiplicative, each emits {gate,value,reason})  q' = q · g_cred · g_xfield · g_sen
        │
        ▼
 [F] GLOBAL CALIBRATION  score₀ = 100·h_mode(q')   → BANDS from precision/recall (advance/REVIEW/discard),
        uncertainty-widened edges; thin / failed-canon / logistics-unknown / high-variance → REVIEW
        │
        ├──── uncertainty gate (band-edge margin OR facet-disagreement OR fusion-vs-RRF rank gap) ────┐
        ▼                                                                                             ▼
 [G] LLM OVERLAY (gated, ≤K): reorder-within-band + explain; consumes facet scores + KG paths only,
       never raw docs; cannot invent a skill or exceed a gate/band; temp=0; permuted criterion order;
       demographic-neutralized; \x1e prompt-cache boundary; deterministic template fallback.
        │
        ▼
 [H] FEEDBACK (Bayesian-shrunk, bounded, decayed; fit-axis only; hash-workable requirement-category channel)
        │
        ▼
   ScoreResult {score, band, reason, match_points, gaps, facets, gates, provenance, calibration}  (§11)
```

Deterministic Stages A–F are the flagship keyless path. G–H are overlays that improve, never gate.

---

## 4. The facets

Notation: candidate CapabilitySet `C`; JD RequirementSet `R`. Both are sets of ESCO concept ids
(with evidence weights on the candidate side, importance weights on the JD side) plus retained
literal phrases (the escape hatch, §5). `sim(a,b)` = cosine in the active `mode`, used **only** in
φ_sem and as one corroboration term in φ_occ. Every facet outputs a **raw** value (Stage B) and a
**confidence** κ; Stage C calibrates raw→f̃.

### 4.1 φ_cov — Requirement coverage (the field-agnostic backbone; embedding-free)

Per requirement `ρ∈R` with importance `imp(ρ)`, the best candidate evidence match — **embedding-free
primary, embedding last**:

```
match(ρ) = max over κ∈C of:
     e(κ)                         if same ESCO id                         (exact,  via="exact")
     e(κ)·decay^hops              if κ reachable from ρ via RELATED_TO ≤2  (graph,  via="hop")
     e(κ)·jacc(ρ,κ)               multilingual-altLabel / token Jaccard    (lexical,via="literal")
     e(κ)·softsim(ρ,κ)·κ_sem      if mode has real embeddings & sim≥τ_link  (embed,  via="embed")
φ_cov = Σ_ρ imp(ρ)·match(ρ) / Σ_ρ imp(ρ)          ∈ [0,1]
```

- `e(κ)` = candidate evidence strength (from φ_proof, §4.3), so coverage is **graded**, not binary presence.
- `imp(ρ)`: must=1.0, weak-must (default) = `imp_default`, nice=0.4. **Must/nice classification is a
  refinement, not a prerequisite** — cues are linguistic (`required/must/essential` vs
  `preferred/bonus/nice to have`), field-agnostic; when no clean section is found (terse/non-English
  JD), everything defaults to weak-must and coverage still computes. Coverage never depends on the
  must/nice classifier working.
- **Field-agnostic:** both sides are ESCO ids or retained literals — no `TECH_TAXONOMY`. A nurse's "IV
  cannulation"↔JD "peripheral cannulation" resolves via `hop`; a welder's "TIG root pass" survives via
  `literal`; a French JD's requirements resolve to the same language-neutral ESCO ids via multilingual
  altLabels.
- **Degradation:** `κ_cov = clip(a + b·extraction_confidence·esco_resolution_rate, 0, 1)`. Terse JD,
  few phrases, or low ESCO-resolution → `κ_cov` low → weight shifts to φ_occ + φ_sem AND the lead
  routes to REVIEW (§8). The embed channel is gated by `κ_sem`, so in hash mode it contributes ≈0 by
  construction — coverage is carried by exact+hop+literal.

### 4.2 φ_occ — Occupation overlap (embedding-free primary; multi-occupation, no smearing)

The keyless cross-field signal and the complement that drives the cross-field gate.

```
O_c = candidate's SET of ESCO occupations (each with evidence-mass weight)   # multi-occupation, NOT one centroid
O_j = JD's ESCO occupation(s) (from title + required skills)
occ_pair(a,b) = graphJaccard( essentialSkills(a)⊕expand, essentialSkills(b)⊕expand )   # id-set overlap, KG-expanded
φ_occ = max over (a∈O_c, b∈O_j) of occ_pair(a,b)
      (+ β_corr·max sim(emb(a),emb(b))·κ_sem   — embedding corroboration ONLY, ~0 in hash)
d_occ = 1 − φ_occ_lexical_component                                          # distance for the gate (§7)
```

- **`max` over a SET of occupations** solves the hybrid/blended-career trap (clinical-informatics =
  {nurse, developer}): a nursing-informatics JD matches the nurse occupation; a dev JD matches the dev
  occupation. No smeared centroid mis-scoring both.
- **graphJaccard is embedding-free** (id-set overlap over ESCO essential-skill sets, expanded by
  `RELATED_TO`), so it is fully reliable in hash mode. Embedding cosine is added only as a
  `β_corr`-weighted corroboration term scaled by `κ_sem` → it vanishes in hash mode.
- **Field-agnostic & symmetric:** welder↔welding and lawyer↔law compute identically; welder↔law and
  lawyer↔welding trip low φ_occ identically. No blocklist. `κ_occ` is high always (keyless).

### 4.3 φ_proof — Evidence depth (graded; uses recovered signals; produces `e(κ)`)

```
tier(κ):  project-with-repo+impact 1.00 | project-with-stack 0.88 | in experience 0.80 |
          listed only 0.55 | latent (reached via hop/embed only) 0.30 | absent 0
e(κ) = tier(κ) · rec(κ) · freq(κ) · ext(κ)            # bounded, capped at 1.0; each modifier ∈ neutral..1.25
   rec(κ)  = f(months_since_use ; half-life h_rec)     # M7; default 1.0 (neutral) if dates unknown
   freq(κ) = 1 + c_freq·min(uses−1, u_cap)             # M6; default 1.0 if freq unrecovered
   ext(κ)  = project-only saturating github+quality     # M9; default 1.0 if unrecovered
φ_proof = Σ_{ρ∈R} imp(ρ)·e(κ*(ρ)) / Σ_ρ imp(ρ)         # evidence behind the matched skills
```

- **Field-agnostic:** tiers/recency/frequency are domain-neutral — a nurse's 20 clinical placements ↔
  a dev's 20 repos score identically.
- **Degradation:** `κ_proof = f(fraction of evidence signals recovered)`; when all default to neutral
  (Phase-0-only), φ_proof reduces to a tier-only score, flagged `evidence_thin`. A 500-star maintained
  repo ≠ a toy once M9 lands.

### 4.4 φ_sen — Seniority fit (parsed durations only; title level-words never set a level)

```
gap = req_years − cand_years                          # cand_years from PARSED exp[i].months (M7), never prose re-parse
φ_sen = exp( −(max(0,gap)/σ_under)² − (max(0,−gap−slack)/σ_over)² )   # two-sided Gaussian tolerance
```

- **Domain-word guard (structurally clean):** the words *senior/junior/lead* in a title contribute a
  level **only if corroborated by a numeric `N+ years` phrase or `seniority_hint`**. "Senior Care
  Assistant" / "Junior School Teacher" never infer a level from the adjective. Title level-words are
  read nowhere as a level.
- Under-qualification penalized sharply (`σ_under` small); over-qualification penalized gently only
  past `slack`.
- **Degradation:** if `req_years` unknown → `φ_sen = NEUTRAL`, `κ_sen=0`, flag `seniority_unstated`.
  No cap fires on absence.

### 4.5 φ_sem — Semantic corroboration (demographic-neutralized; confidence measured, not asserted)

```
raw_sem = 0.6·mean_channel sim(v_c^ch, v_j) + 0.4·peak_channel sim   # keeps the 0.60/0.40 blend & LanceDB channels
```

- Channels scoped to current-profile row ids (stale-vector guard preserved). **All provider-specific
  stretch windows removed** — scale normalization lives entirely in Stage C calibration.
- **Identity neutralization (F10, mandatory, both towers):** strip names/pronouns/photos/addresses/
  emails from profile AND JD text before embedding (and before any LLM call). Test-enforced score
  invariance (§12).
- **`κ_sem` is CALIBRATED per mode, not hardcoded.** It is the measured discriminative reliability
  (AUC-derived) of φ_sem on the golden set in that mode. In hash mode it comes out low (measured —
  "hash cosine ≈ token overlap"), automatically redistributing weight onto φ_cov/φ_occ/φ_proof, and
  sets provenance `semantic_hash_mode`. Honest replacement for both the incumbent's silent 15% channel
  and an asserted fixed `κ_sem`.

### 4.6 φ_log — Logistics (soft facet, never a hard gate)

```
loc = 1 if remote_ok or same region/metro ; 0.5 if same country/adjacent ; 0.15 otherwise
sal = 1 if unknown or overlaps expectation ; 0.4 if below floor
φ_log = w_loc·loc + w_sal·sal   (renormalized over available signals)
```

- Requires M5/M8. **A wrong-country job LOWERS fit but never zeros it** (remote/relocation exist) —
  soft facet, not a gate.
- **Degradation:** JD lacks the columns → `φ_log = NEUTRAL`, `κ_log=0`, flag `logistics_missing`.
  Never fabricates a satisfied logistics (fixes the wrong-country-scores-95 bug honestly).

---

## 5. Skill & taxonomy grounding (offline ESCO on the local MiniLM + Kuzu stack)

This is the substrate that makes every facet field-agnostic; it retires `WRONG_FIELD_TERMS` and
`TECH_TAXONOMY`.

**Ship an offline ESCO pack** (tens of MB) into the existing **Kuzu** graph: ESCO occupation + skill
concepts, `altLabel` synonym table (**multilingual**), `is_licence`/regulated-profession node flags,
`RELATED_TO`/`ESSENTIAL_FOR` edges, plus a precomputed ESCO-label embedding table (used only in ONNX
mode) and a precomputed ESCO **IDF** table (for importance specificity). ESCO is cross-occupational by
design (F6, F8) — nursing, welding, law, teaching all have concept nodes; there is no tech bias
because there is no tech list.

**Canonicalization `raw_mention → esco_id` — a keyless-first cascade (F6, encoder/table, NOT
LLM-per-call):**
1. **Synonym/alias table** (exact + casefold, symbols preserved, **multilingual altLabels**):
   `k8s→Kubernetes`, `RN→Registered Nurse`, `MIG welding→gas metal arc welding`,
   `infirmière→Registered Nurse`. Works in **every mode and language** — the primary path in hash mode.
2. **Embedding NN into ESCO labels — ONNX mode ONLY**, accept if `sim ≥ τ_link` (CALIBRATED per mode).
   **Disabled in hash mode** (hash NN ≈ token overlap; a per-mode threshold cannot rescue it).
3. **Literal escape hatch:** unmatched mentions are **kept as literal phrases** and still participate
   via φ_cov/φ_occ `literal` Jaccard and φ_sem. Nothing is discarded for failing a taxonomy. This
   promotes the incumbent's one good instinct (`candidate_domain_phrases`) to primary.

**Related-skill expansion (F6, KG, offline):** from each canonical id, expand along
`RELATED_TO`/`ESSENTIAL_FOR` ≤2 hops with decay `decay^hops`, bounded fan-out (≤12 neighbors/node →
keeps it O(|skills|·k), not quadratic). Recovers latent skills symmetrically
(`Kubernetes↔container orchestration`, `venipuncture↔phlebotomy`, `GMAW↔structural welding`).

**Importance specificity (no hand-set per-skill numbers):**
`imp(ρ) = base(section) · freq_boost · specificity(ρ)`, where `specificity` reads the precomputed ESCO
**IDF** — a rare licence outweighs generic "communication skills" from data, replacing the incumbent's
`70+min(26,4·|req|)` specificity ceiling.

**Cost note (F6/F7):** a ~109M contrastive bi-encoder (ConTeXT-match class) matches GPT-4 on ESCO
extraction at ~1/7660 the cost. Ship it **only inside the optional ONNX pack** for the tier-2 NN step;
canonicalization is otherwise pure table+graph. **The 2.2GB encoder is never the flagship** — the
flagship is table+graph+literal.

---

## 6. Fusion math (facets → raw quality `q`)

### 6.1 Per-facet calibration (Stage C)
For each facet `f` and each `mode`, fit **isotonic regression** `g_{f,mode}: raw → f̃ ∈ [0,1]` mapping
raw facet values to their quality percentile on the **reference distribution** (§7). Monotone,
non-parametric, no shape assumption, no magic window. This puts hash-cosine (~0.3–0.6) and
ONNX-cosine (~0.1–0.8) on the same rank scale, and makes each facet field-comparable at the facet level.

### 6.2 The combiner — confidence-weighted mean of calibrated facets
```
q = Σ_f (κ_f · w_f) · f̃_f  /  Σ_f (κ_f · w_f)          over facets f ∈ {cov, proof, occ, sem, log},  q ∈ [0,1]
```
- **Confidence κ_f is folded into the denominator:** a NEUTRAL/degraded facet (κ_f→0) drops out and
  its weight **renormalizes automatically onto the confident facets**. Honest degradation becomes a
  math property, not a branch — and it avoids an active-set explosion (no per-active-set curves;
  renormalization does the work).
- Each facet's contribution `(κ_f·w_f·f̃_f)/Σ` is a **reportable number** in the ScoreResult.

### 6.3 The weights `w_f` — principled at every dataset size (no magic constants)
Learn `w_f` by **non-negative MAP logistic/ranking regression** of `good-fit∈{0,1}` on the calibrated
facets over the golden set, with a **Gaussian prior centered on F2-derived seed weights**:
```
seed μ_w (from F2, remapped to our facet set):  cov 0.34, proof 0.20, occ 0.24, sem 0.10, log 0.12
w ~ 𝒩(μ_w, σ²I),  σ set so the prior ≈ 30 effective pseudo-observations
w* = argmax_w  Σ log P(good | q(w))  −  ‖w−μ_w‖²/(2σ²)     s.t.  w_f ≥ 0
```
- **Tiny golden set → prior dominates → weights ≈ the published F2 defaults** (defensible, not
  invented). **Golden set grows → data washes the prior out.** No unexplained magic weight at *any*
  dataset size.
- **Non-negativity** guarantees monotonicity (more coverage never lowers the score).
- Note: **weight is deliberately SPREAD** (cov ≈0.34, not 0.62). No single fragile extraction step is
  a point of failure.

### 6.4 Why this combiner, vs the alternatives
- **vs. incumbent hand-weighted sum of raw facets:** raw facets aren't comparable across fields/modes
  — the root of the "77 vs 84" defect. We sum **calibrated** facets → comparable by construction (§7).
- **vs. pure RRF (F3):** RRF yields **ranks, not a calibrated absolute**, and the product needs an
  absolute 0–100 with a stable threshold, a per-facet breakdown, and the two-axis contract. So RRF
  **informs but does not decide** — used at retrieval/shortlist and as a **cross-check**: compute each
  lead's RRF rank (over facet ranks, `RRF=Σ 1/(60+rank_f)`, `k=60` PRINCIPLED) and its fusion rank; a
  gap >20 percentile raises `fusion_unstable` → feeds the LLM uncertainty gate (§9) and the eval
  ordering locks.
- **vs. fully learned LTR/GBDT/cross-encoder:** **G1** — <100 feedback events and a small golden set →
  a high-capacity learner overfits and loses explainability. A ~5-weight priored logistic is the right
  capacity and stays interpretable.

### 6.5 Gates vs facets
Gates are applied after the mean (§7), then global calibration (§7.3). Gates are multiplicative
guardrails on `q`, **not** facets in the convex sum — because seniority/credential/cross-field are
gates you cannot "buy back" with more of another facet, and multiplication encodes that while staying
bounded (`q' ≤ q`) and explainable.

### 6.6 Constants Register
Every constant is tagged and lives in a single versioned `calibration.json` with value, tag, fit-date,
golden-set-version, per-field validation metric:

| Constant | Tag | How set |
|---|---|---|
| `w_cov, w_proof, w_occ, w_sem, w_log` | SEED→learned | F2-centered Gaussian prior, MAP-logistic fit; washes out with data |
| `κ_sem(mode)`, `κ_cov` params, `κ_proof`, `τ_link(mode)` | CALIBRATED | measured on held-out golden per mode |
| tier values, `σ_under/σ_over/slack`, `decay^hops`, `h_rec`, `c_freq`, `imp_default`, `β_corr`, gate `β`/`gmin` | SEED→CALIBRATED | documented seeds, then fit on the golden set; never hand-frozen |
| RRF `k=60`; isotonic monotonicity; convex-mean renorm | PRINCIPLED | structural |
| band thresholds `B_high/B_low` | CALIBRATED | derived from precision/recall (§8), never hardcoded 76 |

No constant is a hand-tuned magic number relabeled as a "principled decay."

---

## 7. Calibration & guardrails combined flow

### 7.1 Reference distribution (defines SCALE, not TRUTH)
Build a **Reference Corpus 𝓡**: (candidate, job) pairs spanning all field clusters (nursing, trades,
law, sales, teaching, software, admin). **𝓡 MUST include real scraped-noise samples** (terse ATS
stubs, HTML-stripped blobs, non-English postings) — never a purely synthetic/clean distribution, or
the percentile scale is fiction at deploy. 𝓡 is **not** the golden set (avoids circularity): 𝓡 fixes
the *scale*, the golden set fixes the *truth*.

### 7.2 Gates (Stage E) — multiplicative, calibrated, explainable, evidence-overridable
```
q' = q · g_cred · g_xfield · g_sen           each g ∈ [gmin_g, 1], each emits {gate, value, reason}
```
- **`g_cred` — credential / licence gate (the only one handling legal gates).** Driven by the ESCO
  **`is_licence`** node flag — field-agnostic, a node property, not a hardcoded list. `g_cred = 1` if
  no hard-licence requirement or all are evidenced; else down to `gmin_cred` per unmet legally-hard
  licence (RN/CDL/bar/CPA/forklift). **Non-buy-backable:** strong skill coverage cannot lift it.
  Reason: `"×gmin: RN licence required, none found."` `gmin_cred` is CALIBRATED so an unmet hard
  licence lands at/below the advance band.
- **`g_xfield` — cross-field, evidence-override (symmetric, blocklist-free):**
  ```
  g_xfield = 1 − β_xf · d_occ · (1 − max(φ_cov, φ_proof))
  ```
  It bites **only** when the occupation is far (`d_occ` high, from the **embedding-free** graph-Jaccard
  component) **AND** the candidate's evidence does not cover the JD. A career-changer whose ESCO skills
  genuinely cover the JD → `max(φ_cov,φ_proof)` high → penalty **vanishes**. A welder→law and a
  lawyer→welding trip it identically. This is what retires `WRONG_FIELD_TERMS`. Reason:
  `"closest occupation 'X' is distant from 'Y'; 6/8 required competencies unmatched."`
- **`g_sen` — seniority (smooth, from φ_sen):** `g_sen = clip(φ_sen, gmin_sen, 1)`, active only when
  `κ_sen>0`. Under-qual → low; over-qual → ≈1. Never a title-keyword hard cap.

Applying gates in quality space **before** global calibration keeps the final number a calibrated
probability while the gates stay bounded and reason-bearing.

### 7.3 Global calibration (Stage F) — one number, same meaning everywhere
```
score₀ = round( 100 · h_mode(q') )
```
- Fit **isotonic regression `h_mode: q' → P(good-fit)`** on the golden set (§12), **one curve per
  embedding mode** (`h_hash`, `h_onnx`). A "78" then means "≈78% likely a genuine, actionable fit,"
  identically for welder/lawyer/hash/onnx. Monotone → never changes ordering, only the number's meaning.
- **One curve per mode only** — NOT per-active-set, NOT per-field-logic. Field comparability is
  achieved by **measuring** per-field ECE and applying **data-measured** offsets/shrinkage where a
  slice drifts, never by field-specific *code* (§12.3). Platt (1-param sigmoid) is the fallback when
  the golden set is < ~150 graded pairs for stable isotonic.

### 7.4 Comparability audit (hard ship-gate — measured, not asserted; G4)
Before any cut-over: **(a)** per-field mean score within each quality tier — require `|Δmean|` between
any two fields < 5 pts; **(b)** hash-vs-onnx score Spearman ρ ≥ 0.85 and mean `|Δ|` < 6 on the same
pairs; **(c)** top-20 rank agreement Kendall τ ≥ 0.7. Failing (a) → hierarchical **shrinkage**
`h_field = λ·h_global + (1−λ)·h_field_local` (λ from cluster sample size), never raw per-field curves.

---

## 8. Guardrail bands — replacing the hard 76 cliff

Bands are **derived from the golden dev set's precision/recall curve, never hardcoded**:

```
B_high = smallest score with precision(good-fit) ≥ 0.85 on golden dev   → advance (tailoring/matched)
B_low  = largest  score with recall(good-fit)   ≥ 0.90 on golden dev   → below = discard (soft, recoverable)
band:  score ≥ B_high → advance ;  B_low ≤ score < B_high → REVIEW ;  score < B_low → discard
```

- **REVIEW band = surfaced to the user, NEVER auto-deleted.** Borderline/scoring-noise leads land here
  instead of being destroyed.
- **Uncertainty-widened edges:**
  `δ = c1·[hash] + c2·[thin JD] + c3·Var_f(f̃) + c4·[low κ_cov] + c5·[logistics_unknown] + c6·[fusion_unstable]`.
  A lead whose confidence interval overlaps `B_high` routes to REVIEW regardless of point value.
  Consequences:
  - **Thin posting** (JD <160 chars, few requirements) → low `κ_cov`/high `δ` → **REVIEW, not the old
    68 auto-discard.** A terse-but-perfect ATS stub reaches a human.
  - **Failed canonicalization / non-English-unresolvable** → low `κ_cov` → REVIEW.
- All discards are **soft** (recoverable) and ship their trigger in `gates`/`reason`.

---

## 9. LLM overlay (bounded, uncertainty-gated, bias-controlled)

**Role (F1, G2):** explanation refinement + **reorder-within-band** + borderline disambiguation. The
LLM receives **only** pre-computed facet scores + matched/unmatched requirements + KG paths +
neutralized JD/profile snippets — **never raw documents as source of truth.** It **cannot introduce a
skill the matcher didn't find, cannot change a facet value, and cannot lift a lead above its
gate/band.** Its number is used for **relative ordering/bucketing within a band**, fused with the
deterministic rank via RRF — never as a trusted absolute (G2). `_hard_cap` semantics preserved.

**Gating (F4, F5, G3 — cost discipline):** invoke only for
1. REVIEW-band leads, OR
2. high uncertainty (`fusion_unstable`, high facet-variance, or `|score − B| < 4`),
capped at top-K by baseline (`select_llm_eval_targets`, default 25). Confident, agreeing
advance/discard leads skip the LLM entirely. **G3 caveat honored:** the gate's compute-savings are
**validated on the JHM job-fit golden set** (§12.4) before being trusted — not assumed from adjacent
domains.

**Rubric & bias controls (F9 — mandatory):**
- `temperature=0` (pinned) + `seed` if the provider exposes one (G2). Low temp is required for
  structured-output parseability (the one robust F9 temp finding; the "temp↔consistency correlation"
  claim is **refuted** and not relied on).
- **Structured JSON schema** (below); schema violation → deterministic template fallback (F1), no
  retry-drift.
- **Criterion-order bias (F9c):** present score criteria in **randomized order per call**; for
  borderline leads **average over 2–3 permuted criterion orders** (self-consistency).
- **Position bias (F9a):** present the shortlist in randomized order.
- **Demographic neutralization (F10):** names/pronouns/photos/addresses stripped from both profile and
  JD before the call.

**Schema:**
```json
{ "band_move": "up|down|hold", "reason": "...", "match_points": ["..."],
  "gaps": ["..."], "requirement_notes": [{"req":"...","verdict":"met|partial|missing"}],
  "confidence": 0.0-1.0 }
```
`band_move` is a within-band nudge only (F9b: top-1 flips on 16–39% of prompts — we never let the LLM
set the number). **Prompt cache:** keep the `\x1e` boundary — stable rubric + neutralized profile +
prefs prefix cached (Anthropic prompt caching); per-lead JD + facet baseline after.

**Deterministic fallback (F1):** LLM absent / schema violation / parse fail → deterministic template
reason from the matcher. `llm=off` is the flagship path and is fully correct on its own; the overlay
only ever improves prose + within-band ordering. Recorded in `provenance.llm`.

---

## 10. Feedback personalization (conservative — G1)

<100 events is unsupported for LTR (G1) → shrink, bound, decay, cold-start; two axes strictly separate.

- **Two axes, never crossed (R2):** *fit* feedback reweights **requirement-category preferences**
  (which kinds of requirements this user favors) — bounded `±δ_fit` on facet/requirement-category
  weights, re-fused (cannot bypass gates). *Signal* feedback stays on the metadata `feedback_ranker`,
  clamped `±18` on `signal_score`. Content prefs move fit; metadata prefs move signal.
- **Bayesian shrinkage to a neutral prior:** per-feature `θ̂ = Σ decay·polarity / (Σ decay + κ0)`,
  `κ0≈5` pseudo-counts → 1–2 events barely move.
- **Bounded deltas:** fit deltas clamped `±8` (tighter than today's ±12/±18) until ≥ N events/feature.
- **Exponential decay:** half-life ≈ 60 days.
- **Cold-start:** neutral, zero movement until `count ≥ 3` per feature.
- **HASH-WORKABLE fit channel (fixes the flagship-inert defect):** the fit-side content preference is
  expressed as a **requirement-category / facet-space** preference — it works with **no embeddings**,
  replacing the hash-inert `feedback_semantic` direction. When ONNX is present it may additionally use
  the semantic direction; when absent it is honestly the category channel, not silently nothing.
- **Idempotent recompute** from `base_score`/`base_signal_score` preserved (asset) — repeats never
  compound.

---

## 11. The ScoreResult contract

```jsonc
{
  "score": 78,                        // calibrated FIT ∈ [0,100], this axis only (never signal_score)
  "band": "advance|review|discard",   // §8, no silent 76 cliff
  "reason": "Strong skill coverage (6/8 required); evidence thin on 2; seniority fits.",
  "match_points": ["GMAW welding (3 projects)", "blueprint reading", "OSHA cert"],
  "gaps": ["pipe welding (no evidence)", "pressure-vessel certification"],
  "requirement_coverage": {
     "must": {"covered": 0.0-1.0, "n_reqs": int,
              "items": [{"req","canon","evidence_tier","e":0-1,"via":"exact|hop|literal|embed"}]},
     "nice": { ... }
  },
  "facets": {                         // each: calibrated value, confidence, fusion contribution, flags
     "cov":  {"raw":0.75,"cal":0.72,"kappa":0.9,"contrib":+0.31,"flags":[]},
     "proof":{"raw":0.40,"cal":0.38,"kappa":0.6,"contrib":+0.08,"flags":["evidence_thin"]},
     "occ":  {"raw":0.71,"cal":0.68,"kappa":1.0,"contrib":+0.24,"flags":[]},
     "sem":  {"raw":0.62,"cal":0.60,"kappa":0.2,"contrib":+0.04,"flags":["semantic_hash_mode"]},
     "log":  {"kappa":0.0,"flags":["logistics_missing"]}       // NEUTRAL → dropped from fusion
  },
  "gates": [ {"gate":"cross_field","value":1.0,"reason":"same-field"},
             {"gate":"credential","value":0.30,"reason":"RN licence required, none found"},
             {"gate":"seniority","value":0.92,"reason":"mid vs required 3+ yrs"} ],
  "applied_cap": "credential",        // BACK-COMPAT: dominant gate (harness reads .score + .applied_cap)
  "cap_kinds": ["credential"],        // BACK-COMPAT
  "confidence": { "embedding_mode":"hash", "onnx_present":false, "llm_used":false,
                  "extraction_confidence":0.7, "esco_resolution_rate":0.6,
                  "degradations":["semantic_hash_mode","logistics_missing","evidence_thin"],
                  "fusion_unstable":false },
  "calibration": {"mode":"hash","h_curve":"h_hash_v3","B_high":74,"B_low":58,"weights_id":"w_v3"},
  "base_score": 78, "base_signal_score": 71   // idempotent feedback recompute anchors (preserved)
}
```
Superset of today's `{score, reason, match_points, gaps, criteria, applied_cap, cap_kinds}` → the eval
harness (`.score`/`.applied_cap`) and ApprovalDrawer keep working. The UI renders `facets` as a
contribution bar, `gates` as reason chips, `degradations` as honest badges ("Semantic in fast/offline
mode"), and REVIEW as a distinct triage lane.

---

## 12. Evaluation & regression harness (non-circular by construction)

The incumbent corpus is calibrated off the incumbent engine (golden bounds = engine output +
headroom), so a *better* engine fails for being better. Replace with:

### 12.1 Independent graded golden set
150–300 (cv, job) pairs, relevance graded **0–3 by a human/rubric blind to any engine output** (grades
from ESCO occupation+skill overlap ground truth + human adjudication). **Field-balanced:** ≥60 pairs
per cluster (nursing, trades, law, sales, teaching, software, admin) + cross-field + seniority-trap +
credential-trap + non-English + demographic-swap pairs. **Skill-disjoint train/dev/test splits** (F11)
so no skill leaks into learned weights or calibration.

### 12.2 Metrics (F11)
NDCG@{5,10}, MRR, precision@{5,10}, recall@{10} — **overall and per-field slice** (G4). Report the
precision/recall tradeoff explicitly (pruning trades recall for precision). Retire the binary
`ACCURACY_FLOOR=1.0` gate (it blocks hard middle cases); replace with metric thresholds + regression
deltas vs the last release; allow ambiguous mid-band cases graded 1–2.

### 12.3 Cross-field & cross-mode honesty (measured, not asserted)
- Per-field ECE **and** per-embedding-mode ECE; ship-gate = no field cluster's NDCG@10 more than 0.05
  below the macro-average, and the §7.4 comparability audit passes.
- Field offsets are **data-measured** only; no field-specific logic.
- **Direct pairwise ordering locks** (not band-overlap): explicit `(pair, must_rank_above)` invariants
  — `nurse↔nursing > nurse↔software`, `welder↔welding > welder↔law` — checked by **direct score
  comparison**, verified in **all four modes** (LLM×{on,off} × embedding×{onnx,hash}). These encode the
  GOAL.md invariants.

### 12.4 Bias & robustness tests
- **F10 counterfactual fairness:** swap demographic-associated names/pronouns/addresses on fixed
  CVs+JDs → require `|Δscore| < 1` (neutralization working); run intersectional swaps.
- **Uncertainty-gate validation (G3):** gating the LLM to uncertain leads must match within 0.01 NDCG
  of always-LLM while cutting calls ≥15%, on **our** golden set, before trusting savings.
- **Determinism (G2):** same lead ×5 at temp 0 → identical deterministic score; LLM rank-hint variance
  bounded.
- **Calibration monitoring:** golden set versioned; adding a case requires a blind grade first;
  weights/calibration refit on train/dev, evaluated on the untouched test split — the harness never
  tunes on its own test set. Reuse the engine-agnostic `evals/harness.py`.

---

## 13. Phased implementation roadmap (nothing breaks `main`)

- **Phase 0 — source-integrity + migration (ships alone, first, safely; already improves cross-field
  correctness).** §2 M1–M10: ESCO-id skill keying (fixes C/C++/C#), kill the lowercase/tech-only
  `_valid_skill` gate, negation scan, unify parser caps, `005_add_fit_columns.sql`, recover
  freq/stars/dates/quality/per-role location, replace-by-version snapshot merge. Land the
  **independent golden set + harness** (§12) behind a flag in parallel. Files: `profile/normalization.py`,
  `ranking/scoring_engine.py`, `profile/ingest_store.py`, snapshot builder,
  `data/sqlite/migrations/005_add_fit_columns.sql`, `evals/harness.py`. **This alone stops a large
  class of silent mis-scores with zero fusion change.**
- **Phase 1 — ESCO pack + retire the blocklist (highest correctness ROI).** Ship the offline ESCO pack
  (multilingual altLabels, `is_licence` flags, `RELATED_TO`) into Kuzu; wire canonicalization + hop
  expansion; replace `WRONG_FIELD_TERMS` + literal-overlap with symmetric **φ_occ + φ_cov + g_xfield**.
  Run **shadow** (compute alongside incumbent, log both). Files: `ranking/scoring_engine.py`,
  `ranking/semantic.py`, Kuzu loader.
- **Phase 2 — facets + confidence-weighted priored fusion + per-mode calibration + review band.** Ship
  φ_cov/φ_proof/φ_occ/φ_sem/φ_log with κ, per-facet + global isotonic per mode, priored MAP-logistic
  weights, gates (incl. `g_cred`), three-way bands from precision/recall. Retire the magic weight
  branches, stretch windows, `min()` ladder, 76 cliff. Cut over behind a `scoring_engine_version` flag
  only when ordering-locks + per-field NDCG + the §7.4 comparability audit pass in all four modes.
- **Phase 3 — LLM overlay + hash-workable feedback.** Uncertainty-gated, bias-controlled,
  template-fallback overlay (§9); Bayesian-shrunk bounded decayed feedback with the requirement-category
  fit channel (§10).
- **Phase 4 — ONNX + contrastive encoder.** Ship the ONNX pack + ConTeXT-match encoder; activate mode-
  `onnx` calibration curves and tier-2 embedding-NN canonicalization. Hash mode remains a first-class,
  calibrated, honest fallback.

Each phase is independently revertible via its flag; the deterministic keyless path is fully functional
after **Phase 2**, before any LLM work.

---

## 14. Where it can still be wrong + open questions (honoring G1–G4)

1. **ESCO coverage gaps (G4).** ESCO is EU-centric and software/knowledge-work-richer than
   trades/informal/regional roles. A niche welding sub-discipline, a non-EU credential, or an emerging
   framework may lack ids/edges → φ_cov leans on the literal + multilingual-altLabel Jaccard, which on
   **hash** is the weakest seam. Flagged `skill_extraction_lossy`; **measure per-field ECE — do not
   trust cross-field calibration for an under-sampled field until proven.**
2. **Hash-mode semantic is genuinely weaker.** Calibration makes φ_sem *comparable* and *honest*
   (flagged) but cannot manufacture discriminative signal that isn't there; for sparse-coverage roles,
   hash-mode within-tier ranking is noisier than ONNX. Surfaced, not hidden. This is why cross-field
   rests on φ_cov/φ_occ (embedding-free), not φ_sem.
3. **Cross-lingual hash is the hardest case.** A French JD ↔ English CV shares ~0 tokens; we rescue it
   via multilingual-altLabel canonicalization to shared ESCO ids, but a mention absent from ESCO in
   that language falls through. Measured per-field/per-language ECE; the ONNX pack is genuinely better
   here and we say so.
4. **Requirement extraction on messy JDs.** Noun-chunking mis-splits conjoined bullets or misses
   implied must-haves. Mitigated by: weight spread (φ_cov ≈0.34, not dominant), coverage not depending
   on must/nice classification, `extraction_confidence` surfaced, low-confidence → REVIEW. But a
   normal-length noisy JD can still emit a confident-ish wrong number if extraction silently
   half-succeeds.
5. **Credential detection variance.** `g_cred` relies on ESCO `is_licence` flags — an unflagged legal
   licence under-gates; an over-flagged "certification preferred" over-gates. Highest-variance gate;
   audited against the credential-trap golden slice.
6. **Occupation inference at the root.** `g_xfield` and φ_occ assume `O_c`/`O_j` are right; a sparse
   profile or a JD that lists a role it doesn't mean can mis-set them. Multi-occupation representation
   + evidence-override limit the blast radius but cannot fully rescue a wrong root.
7. **Calibration is only as honest as 𝓡 + the golden set.** Thin per-field coverage → unstable curves
   and wide-CI ECE; a field we under-sample stays possibly mis-calibrated (G4 is *measured*, not
   *solved*). Report CIs; grow under-sampled clusters first.
8. **Learned weights need volume (G1).** Until the golden set is large, weights sit near the F2 prior —
   defensible, not optimal per field; and feedback is deliberately weak at <100 events. Some users will
   find early personalization "generic" — the correct conservative trade, a real UX tension, not a bug.
9. **LLM ordering non-determinism (G2).** temp=0 + permuted-order averaging + within-band clamping +
   RRF fusion reduce but don't eliminate run-to-run drift; blast radius is bounded to intra-band
   reordering, never a fabricated advance.
10. **Uncertainty-gate savings unproven for job-fit (G3).** Treated as unvalidated until §12.4 proves
    it on our own golden set.

**Open questions:** (a) minimum 𝓡 size for stable per-mode isotonic before Platt fallback is
unnecessary; (b) whether a small contrastive fine-tune of the ONNX encoder on ESCO occupation↔skill
pairs (ConFit-style, developer-side, inference-only on device) materially lifts non-tech per-field ECE
enough to justify the pack size; (c) the right `κ0`/decay half-life once real feedback volume is
observed — currently seeds.

---

## Appendix A — Research findings referenced (F1–F11, G1–G4)

Verified (3-vote adversarial) SOTA findings that justify the design choices above; peer-reviewed
sources marked ‡.

- **F1** — Gate the LLM downstream of deterministic scoring; it explains / reorders a small set, never
  invents skills or inflates scores; deterministic template fallback. (JobMatchAI; KG-First/LLM-Fallback)
- **F2** — Transparent weighted-sum utility over named interpretable factors (skill/experience/location/
  salary/semantic/company); default weights are a choice, not an optimum → learn/calibrate.
- **F3** — Hybrid fusion `α·norm(lex)+(1−α)·norm(sem)`, but fixed-α min-max is often suboptimal vs RRF /
  query-adaptive α (JobMatchAI itself uses RRF).
- **F4** — Reranking is non-monotonic; gate the expensive stage on a cheap uncertainty signal (15–80%
  compute saved).
- **F5** — Retrieve-then-rerank is canonical (bi-encoder top-K → cross-encoder shortlist). (SBERT)
- **F6** — Field-agnostic skill matching = ESCO canonicalization + RELATED_TO KG expansion + contrastive
  bi-encoder; 109M encoder ≈ GPT-4 at ~1/7660 cost; JobBERT-V2 asymmetric title/skill space.
- **F7** — Training strategy > model size (TalentCLEF'25: 500M contrastive > 7B decoder).
- **F8‡** — ConFit: paraphrase augmentation + contrastive in-batch negatives → +19–31% nDCG@10. (RecSys'24)
- **F9** — LLM-as-judge structural biases: rubric position bias (model-specific), criterion-order bias
  (orthogonal), low temp required for parseable structured output; top-1 flips on 16–39% of prompts.
- **F10‡** — Embedding retrieval has compounding demographic bias (White-name 85.1%, female 11.1%,
  Black-male disadvantaged up to 100%); neutralize identity signals. (AIES'24)
- **F11** — Golden datasets + NDCG/MRR/precision/recall, skill-disjoint splits, honest precision/recall
  tradeoff reporting.
- **G1** — Tiny-feedback personalization (<100 events) is unsupported by the corpus → be conservative
  (Bayesian shrinkage, bounded deltas, decay).
- **G2** — LLM run-to-run determinism beyond temperature unresolved → use for ordering/bucketing +
  calibration, not as a trusted absolute.
- **G3** — Uncertainty-gated reranking proven only in adjacent domains → validate for job-fit before
  trusting savings.
- **G4** — Cross-field calibration is asserted, not demonstrated → measure per-field, don't assume.

_Two claims were adversarially REFUTED and are deliberately NOT relied on: (a) that TalentCLEF'25
validated a bi-encoder+LLM-reranker specifically for candidate-to-job matching; (b) a near-perfect
temperature↔judge-consistency correlation. Only the robust temperature finding (low temp → parseable
output) is used._
