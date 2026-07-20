"""Field-agnostic text utilities for the Coverage-Grounded Fit Engine (CGFE).

Everything here is deliberately domain-neutral: no tech vocabulary, no profession
list. Phrases come from the candidate's OWN profile and the job's OWN text, so the
same code works for nursing, welding, law, teaching, and software.
"""
from __future__ import annotations

import re

# ── Identity neutralization (research F10: embedding/LLM inputs must not carry
#    demographic signal) ───────────────────────────────────────────────────────
_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(?:\+?\d[\d\s().-]{7,}\d)")
_URL_RE = re.compile(r"https?://[^\s|)]+|www\.[^\s|)]+", re.I)

# Generic English filler that carries no matching signal. Field-neutral by design.
_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "and", "the", "or", "of", "to", "in", "on", "for", "with", "at", "by",
    "from", "as", "is", "are", "be", "being", "been", "was", "were", "will", "would",
    "our", "your", "their", "his", "her", "its", "we", "you", "they", "this", "that",
    "these", "those", "it", "have", "has", "had", "do", "does", "did", "can", "could",
    "should", "must", "may", "might", "using", "used", "use", "work", "working",
    "experience", "experienced", "skills", "skill", "knowledge", "proficient",
    "proficiency", "strong", "excellent", "good", "great", "basic", "advanced",
    "ability", "including", "etc", "various", "other", "team", "role", "job",
    "candidate", "responsibilities", "requirements", "required", "preferred", "plus",
    "years", "year", "months", "month", "who", "what", "which", "when", "where",
})


def strip_identity(text: str) -> str:
    """Remove emails / phones / URLs so downstream embedding + LLM inputs carry no
    contact or demographic identifiers (research F10)."""
    if not text:
        return ""
    text = _EMAIL_RE.sub(" ", text)
    text = _URL_RE.sub(" ", text)
    text = _PHONE_RE.sub(" ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize_phrase(value: object) -> str:
    """Lowercase, collapse whitespace, keep alphanumerics + a few skill symbols.

    Preserves ``+`` / ``#`` / ``.`` so "c++", "c#", "node.js" survive; drops other
    punctuation. This is the canonical form phrases are compared in.
    """
    text = re.sub(r"[^a-z0-9+#./ -]", " ", str(value or "").lower())
    text = text.replace("/", " ").replace("-", " ")
    return re.sub(r"\s+", " ", text).strip()


def tokens(value: object) -> set[str]:
    """Content tokens of a phrase (stopwords + <2-char noise removed)."""
    out: set[str] = set()
    for tok in normalize_phrase(value).split():
        tok = tok.strip(".")
        if len(tok) >= 2 and tok not in _STOPWORDS:
            out.add(tok)
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / len(a | b)


def overlap_coeff(a: set[str], b: set[str]) -> float:
    """Szymkiewicz-Simpson overlap coefficient — |A∩B| / min(|A|,|B|).

    Better than Jaccard when the two sets differ greatly in size (a short JD
    requirement vs a rich candidate profile): a fully-contained small set scores 1.0.
    """
    if not a or not b:
        return 0.0
    return len(a & b) / min(len(a), len(b))


def phrase_match(req: str, cand: str) -> float:
    """Directional, embedding-free match strength in [0,1] between a REQUIREMENT phrase
    and a candidate CAPABILITY phrase. Field-agnostic:

    1.0   exact normalized equality
    0.9   requirement fully contained in the capability ("patient care" ⊂ "icu patient
          care") — the requirement is fully addressed by a richer capability
    0.75  capability is a subset of a broader requirement — the candidate has only part
    0.55/0.5  a SINGLE shared token — weak and coincidental ("planning" in "sprint
          planning"), so it earns little
    else  token Jaccard (partial lexical overlap)
    """
    rn, cn = normalize_phrase(req), normalize_phrase(cand)
    if not rn or not cn:
        return 0.0
    if rn == cn:
        return 1.0
    rt, ct = tokens(req), tokens(cand)
    if not rt or not ct:
        return 0.0
    if rt <= ct:          # requirement fully present inside the capability
        return 0.9 if len(rt) >= 2 else 0.55
    if ct <= rt:          # candidate covers only a subset of the requirement
        return 0.75 if len(ct) >= 2 else 0.5
    return jaccard(rt, ct)


# ── Requirement / capability phrase harvesting ─────────────────────────────────
_SPLIT_RE = re.compile(r"[,;/|•·]|\band\b|\bor\b|\n|\.")
_EDGE_RE = re.compile(r"^[\s:\-]+|[\s:\-]+$")  # strip leading/trailing space, colons, hyphens
# Importance cues (linguistic, field-agnostic). Presence RAISES a requirement's weight;
# absence just means "default weak-must" — coverage never depends on this classifying.
_MUST_CUES = ("required", "must have", "must", "essential", "mandatory", "need", "minimum")
_NICE_CUES = ("preferred", "nice to have", "bonus", "plus", "a plus", "desirable", "ideally")


def split_phrases(text: str, *, max_words: int = 6, cap: int = 60) -> list[str]:
    """Split free text into candidate skill/requirement phrases (≤ ``max_words``
    content words each), field-agnostically. Long prose clauses are dropped — they
    are sentences, not competencies."""
    out: list[str] = []
    seen: set[str] = set()
    for raw in _SPLIT_RE.split(text or ""):
        phrase = _EDGE_RE.sub("", re.sub(r"\s+", " ", raw))
        if not phrase:
            continue
        norm = normalize_phrase(phrase)
        content = [t for t in norm.split() if t not in _STOPWORDS]
        if not content or len(content) > max_words:
            continue
        key = " ".join(content)
        if len(key) < 2 or key in seen:
            continue
        seen.add(key)
        out.append(phrase.strip())
        if len(out) >= cap:
            break
    return out


def importance_of(context: str, default: float) -> float:
    """Requirement importance from surrounding linguistic cues (not a taxonomy)."""
    low = (context or "").lower()
    if any(cue in low for cue in _NICE_CUES):
        return 0.4
    if any(cue in low for cue in _MUST_CUES):
        return 1.0
    return default
