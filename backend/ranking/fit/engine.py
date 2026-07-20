"""Coverage-Grounded Fit Engine (CGFE) — the field-agnostic candidate↔job scorer.

See docs/FIT_EVALUATION_ALGORITHM.md for the full design. This module is the
deterministic, keyless flagship path (Stages A-F): parse → facets → confidence-
weighted fusion → smooth gates → seeded calibration → bands → ScoreResult.

Field-agnostic BY CONSTRUCTION: there is no profession list and no tech-only
taxonomy anywhere below. "Wrong field" is the low-coverage + far-occupation corner,
reached symmetrically — a nurse scores a nursing job and a welder a welding job with
the identical code, and each scores the other's job low.

Constants are tagged PRINCIPLED (structural), SEED (documented prior, to be replaced
by a golden-set fit) or CALIBRATED. With no golden set yet, calibration is the
documented SEED identity map; the fusion weights sit at their published prior. Every
number here is honest about which it is.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from core.types import CriterionScore, ScoreResult
from ranking.fit.extract import (
    CapabilitySet,
    RequirementSet,
    build_capability_set,
    build_requirement_set,
)
from ranking.fit.text import overlap_coeff, phrase_match, tokens

# ── Fusion weights (SEED; design §6.3 F2-remapped Gaussian prior mean) ──────────
_W = {"cov": 0.34, "proof": 0.20, "occ": 0.24, "sem": 0.10, "log": 0.12}

# Gate seeds (SEED → CALIBRATED once a golden set exists)
_BETA_XFIELD = 0.95     # cross-field penalty strength
# Occupation deadzone: the cross-field penalty engages only once occupation proximity
# drops BELOW this floor. Above it the two are the same (or an adjacent) kind of work,
# so an in-field junior or a career-adjacent candidate is never labelled wrong-field;
# only a genuinely distant occupation (occ≈0) is. SEED.
_OCC_FLOOR = 0.35
_GMIN_SEN = 0.30        # floor of the smooth seniority gate
_GMIN_CRED = 0.35       # unmet hard-licence multiplier (non-buy-backable)

# Seniority tolerance (SEED). Under-qualification falls off sharply (a fresher against a
# 3+ year role should not read as a fit); over-qualification is barely penalized — a
# job-seeker can always apply to a role below their level.
_SIGMA_UNDER = 2.0
_SIGMA_OVER = 10.0
_SLACK_OVER = 2.0

# SEED calibration (design §7.3 Platt fallback): a logistic that stretches the raw
# fused range so a genuine same-field match (q'≈0.5-0.65) reads as a strong score and a
# gated cross-field lead (q'≈0.05) reads low. Replaced by an isotonic h_mode fit per
# embedding mode once an independent golden set exists. Anchored at h(0.35)=45 (review
# edge), h(0.55)=72, h(0.70)=85.
_CAL_K = 5.7
_CAL_Q0 = 0.385

# Bands (SEED; design §8 — derived from precision/recall once a golden set exists)
_B_HIGH = 70
_B_LOW = 45


@dataclass
class Facet:
    key: str
    value: float          # raw ∈ [0,1]
    kappa: float          # confidence ∈ [0,1]
    reason: str = ""
    flags: list[str] = field(default_factory=list)


@dataclass
class FitResult:
    score: int
    band: str                       # "advance" | "review" | "discard"
    q: float                        # fused, pre-calibration quality ∈ [0,1]
    facets: list[Facet]
    gates: list[dict]               # {gate, value, reason}
    covered: list[tuple[str, float, str]]   # (requirement, strength, via)
    missing: list[str]
    reason: str
    provenance: dict


# ── embedding (optional; honest degradation) ───────────────────────────────────
def _semantic(profile_text: str, jd_text: str) -> tuple[float, float, str]:
    """Return (cosine, kappa, mode). kappa reflects provider reliability: real
    semantic vectors are trusted, the always-available hash embedder is not (its
    cosine ≈ token overlap — research), so it barely moves the fused score."""
    if len(profile_text) < 20 or len(jd_text) < 20:
        return 0.0, 0.0, "none"
    try:
        from data.vector.embeddings import active_provider, embed_texts
        provider = active_provider()
        vecs = embed_texts([profile_text[:2000], jd_text[:2000]])
        if not vecs or len(vecs) < 2:
            return 0.0, 0.0, "none"
        a, b = vecs[0], vecs[1]
        na = math.sqrt(sum(x * x for x in a)) or 1.0
        nb = math.sqrt(sum(x * x for x in b)) or 1.0
        cos = max(0.0, min(1.0, sum(x * y for x, y in zip(a, b, strict=False)) / (na * nb)))
        kappa = 0.9 if provider in {"onnx", "openai", "sentence-transformer"} else 0.15
        return cos, kappa, provider
    except Exception:
        return 0.0, 0.0, "none"


# ── facets ─────────────────────────────────────────────────────────────────────
def _coverage_and_proof(reqs: RequirementSet, caps: CapabilitySet):
    """φ_cov (presence, evidence-blind) and φ_proof (evidence depth) in one pass.

    presence(r) = best phrase-match of r against any capability (is it addressed?)
    e(r)        = presence-match x that capability's evidence tier (is it proven?)
    Both are importance-weighted means over requirements.
    """
    cap_list = caps.phrases()
    if not reqs.items:
        return (Facet("cov", 0.5, 0.0, "no explicit requirements parsed", ["reqs_thin"]),
                Facet("proof", 0.5, 0.0, "no explicit requirements parsed", ["reqs_thin"]),
                [], [])
    imp_sum = sum(r.importance for r in reqs.items) or 1.0
    pres_acc = proof_acc = 0.0
    covered: list[tuple[str, float, str]] = []
    missing: list[str] = []
    for r in reqs.items:
        best_pres = 0.0
        best_e = 0.0
        best_cap = None
        via = "none"
        for cap in cap_list:
            if r.canon == cap.canon:
                pres, v = 1.0, "exact"
            else:
                pres, v = phrase_match(r.display, cap.display), "lexical"
            if pres <= 0:
                continue
            e = pres * cap.tier
            if e > best_e:
                best_e, best_pres, best_cap, via = e, pres, cap, v
        pres_acc += r.importance * best_pres
        proof_acc += r.importance * best_e
        if best_pres >= 0.5 and best_cap is not None:
            covered.append((r.display, best_pres, via))
        elif r.importance >= 0.7:
            missing.append(r.display)
    phi_cov = pres_acc / imp_sum
    phi_proof = proof_acc / imp_sum
    # κ_cov reflects extraction confidence: thin JDs / few requirements are less trustworthy.
    kappa_cov = 0.5 if reqs.thin else 1.0
    covered.sort(key=lambda x: -x[1])
    return (
        Facet("cov", phi_cov, kappa_cov, f"{len(covered)}/{len(reqs.items)} requirements addressed"),
        Facet("proof", phi_proof, 1.0 if cap_list else 0.0, "evidence depth behind matched requirements"),
        covered,
        missing,
    )


def _occupation(reqs: RequirementSet, caps: CapabilitySet) -> Facet:
    """φ_occ — symmetric, embedding-free occupation proximity.

    max of (a) job-title ↔ candidate-role-title token overlap and (b) requirement ↔
    capability token overlap. High when both sides are the same KIND of work; ~0
    across genuinely different professions. Drives the cross-field gate.
    """
    title_sim = overlap_coeff(reqs.title_tokens, caps.role_tokens)
    cap_tokens: set[str] = set()
    for cap in caps.phrases():
        cap_tokens |= tokens(cap.display)
    req_tokens: set[str] = set()
    for r in reqs.items:
        req_tokens |= tokens(r.display)
    field_sim = overlap_coeff(req_tokens, cap_tokens)
    phi = max(title_sim, field_sim)
    return Facet("occ", phi, 1.0, f"occupation proximity (title {title_sim:.2f}, field {field_sim:.2f})")


def _seniority(reqs: RequirementSet, caps: CapabilitySet) -> Facet:
    if reqs.req_years <= 0:
        return Facet("sen", 0.75, 0.0, "no seniority requirement stated", ["seniority_unstated"])
    cand_years = caps.work_months / 12.0
    gap = reqs.req_years - cand_years
    under = max(0.0, gap) / _SIGMA_UNDER
    over = max(0.0, -gap - _SLACK_OVER) / _SIGMA_OVER
    phi = math.exp(-(under * under) - (over * over))
    rel = "under-qualified" if gap > 0 else ("over-qualified" if -gap > _SLACK_OVER else "fits")
    return Facet("sen", phi, 1.0, f"{cand_years:.1f}y vs required {reqs.req_years}y ({rel})")


def _logistics() -> Facet:
    # v1: location/salary/remote are not reliably in the ranking contract yet
    # (design M5/M8). Emit NEUTRAL + flag rather than fabricate a satisfied logistic.
    return Facet("log", 0.7, 0.0, "logistics data not available", ["logistics_missing"])


# ── gates ───────────────────────────────────────────────────────────────────────
def _credential_satisfied(reqs: RequirementSet, caps: CapabilitySet) -> bool:
    if not reqs.licence_tokens:
        return True
    holder = caps.credential_tokens | caps.role_tokens
    for cap in caps.phrases():
        holder |= tokens(cap.display)
    return bool(reqs.licence_tokens & holder)


def _gates(reqs: RequirementSet, caps: CapabilitySet, phi_cov: float, phi_proof: float, phi_occ: float):
    gates: list[dict] = []
    g_total = 1.0

    # cross-field, evidence-overridable (symmetric, blocklist-free). Distance counts
    # only once occupation proximity falls below _OCC_FLOOR (deadzone), so same-field
    # and adjacent candidates are never penalized — only genuinely distant occupations.
    d_occ = max(0.0, (_OCC_FLOOR - phi_occ) / _OCC_FLOOR)
    g_xf = 1.0 - _BETA_XFIELD * d_occ * (1.0 - max(phi_cov, phi_proof))
    g_xf = max(0.05, min(1.0, g_xf))
    if g_xf < 0.85:
        gates.append({"gate": "cross_field", "value": round(g_xf, 3),
                      "reason": f"different occupation and low coverage (occ {phi_occ:.2f}, cov {phi_cov:.2f})"})
    g_total *= g_xf

    # seniority (smooth)
    sen = _seniority(reqs, caps)
    if sen.kappa > 0:
        g_sen = _GMIN_SEN + (1.0 - _GMIN_SEN) * sen.value
        if g_sen < 0.9:
            gates.append({"gate": "seniority", "value": round(g_sen, 3), "reason": sen.reason})
        g_total *= g_sen

    # credential / licence (non-buy-backable)
    if reqs.hard_licence and not _credential_satisfied(reqs, caps):
        gates.append({"gate": "credential", "value": _GMIN_CRED,
                      "reason": "a licence/registration is required and none is evidenced"})
        g_total *= _GMIN_CRED

    return g_total, gates


# ── fusion + calibration ─────────────────────────────────────────────────────────
def _fuse(facets: list[Facet]) -> float:
    num = den = 0.0
    for f in facets:
        w = _W.get(f.key, 0.0) * f.kappa
        num += w * f.value
        den += w
    return (num / den) if den else 0.0


def _calibrate(q_gated: float) -> int:
    # SEED logistic calibration (design §7.3 Platt fallback). Monotone in q', so it
    # never changes ordering — only what the number means. Replaced by an isotonic
    # h_mode fit per embedding mode once an independent golden set exists.
    return max(0, min(100, round(100.0 / (1.0 + math.exp(-_CAL_K * (q_gated - _CAL_Q0))))))


def _band(score: int, facets: list[Facet]) -> str:
    # Uncertainty-widened edges: low-confidence coverage routes a near-advance lead
    # to REVIEW rather than auto-advancing or auto-discarding (design §8).
    cov = next((f for f in facets if f.key == "cov"), None)
    uncertain = bool(cov and cov.kappa < 0.75)
    if score >= _B_HIGH and not uncertain:
        return "advance"
    if score >= _B_LOW or (score >= _B_HIGH and uncertain):
        return "review"
    return "discard"


def evaluate_fit(jd: str, candidate_data: dict, settings: dict | None = None) -> FitResult:
    reqs = build_requirement_set(jd)
    caps = build_capability_set(candidate_data or {})

    cov, proof, covered, missing = _coverage_and_proof(reqs, caps)
    occ = _occupation(reqs, caps)
    sen = _seniority(reqs, caps)
    log = _logistics()
    cos, ksem, mode = _semantic(caps.profile_text, reqs.jd_text)
    sem = Facet("sem", cos, ksem, f"semantic similarity ({mode})",
                ["semantic_hash_mode"] if 0 < ksem < 0.5 else ([] if ksem else ["semantic_unavailable"]))

    facets = [cov, proof, occ, sem, log, sen]
    q = _fuse([cov, proof, occ, sem, log])   # seniority enters via its gate, not the mean
    g_total, gates = _gates(reqs, caps, cov.value, proof.value, occ.value)
    q_gated = q * g_total
    score = _calibrate(q_gated)
    band = _band(score, facets)

    reason = _summarize(cov, proof, occ, covered, missing, gates, band)
    provenance = {
        "engine": "cgfe",
        "embedding_mode": mode,
        "degradations": sorted({fl for f in facets for fl in f.flags}),
        "req_count": len(reqs.items),
        "thin": reqs.thin,
    }
    return FitResult(score, band, q_gated, facets, gates, covered, missing, reason, provenance)


def _summarize(cov, proof, occ, covered, missing, gates, band) -> str:
    bits = [f"CGFE fit {band}: coverage {cov.value:.0%}, evidence {proof.value:.0%}, "
            f"occupation match {occ.value:.0%}."]
    if covered:
        bits.append("Covered: " + ", ".join(c[0] for c in covered[:4]) + ".")
    if missing:
        bits.append("Missing: " + ", ".join(missing[:4]) + ".")
    if gates:
        bits.append("Limits: " + "; ".join(g["reason"] for g in gates[:2]) + ".")
    return " ".join(bits)[:500]


# ── back-compat ScoreResult adapter (drop-in for score_job_lead) ─────────────────
def score_fit(jd: str, candidate_data: dict, settings: dict | None = None) -> ScoreResult:
    """Field-agnostic replacement for ranking.scoring_engine.score_job_lead, returning
    the same ScoreResult contract (``.score`` + ``.applied_cap`` preserved for the eval
    harness and the leads consumer)."""
    r = evaluate_fit(jd, candidate_data, settings)

    criteria = [
        CriterionScore(
            {"cov": "Requirement coverage", "proof": "Proof of work", "occ": "Occupation match",
             "sem": "Semantic fit", "log": "Constraints", "sen": "Seniority fit"}[f.key],
            round(100 * f.value),
            round(100 * _W.get(f.key, 0.0)),
            f.reason,
        )
        for f in r.facets
    ]
    match_points = [f"{disp} ({via})" for disp, _s, via in r.covered[:6]] or \
        [f"{c.name} {c.score}/100" for c in criteria if c.score >= 60][:4]
    gaps = [f"Missing: {m}" for m in r.missing[:5]]
    gaps += [f"{g['gate']} limit: {g['reason']}" for g in r.gates]

    # Back-compat cap semantics: a materially-biting gate reads as a "cap" (the eval
    # harness treats applied_cap-not-None as "a cap fired").
    applied_cap = r.score if r.gates else None
    cap_kinds = [{"cross_field": "wrong-field", "seniority": "seniority",
                  "credential": "credential"}.get(g["gate"], g["gate"]) for g in r.gates]

    return ScoreResult(
        score=r.score,
        reason=r.reason,
        match_points=match_points,
        gaps=list(dict.fromkeys(gaps))[:8],
        criteria=criteria,
        applied_cap=applied_cap,
        cap_kinds=cap_kinds,
    )
