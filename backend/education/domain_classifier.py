"""Domain classifier — maps job text to Mon Master academic domains."""
from __future__ import annotations

# Keyword → Mon Master domain text mapping
# Mon Master uses full domain names like "SCIENCES, TECHNOLOGIES, SANTÉ"
_DOMAIN_KEYWORDS: dict[str, str] = {
    # Informatique / Tech
    "informatique": "SCIENCES, TECHNOLOGIES, SANT",
    "développeur": "SCIENCES, TECHNOLOGIES, SANT",
    "developpeur": "SCIENCES, TECHNOLOGIES, SANT",
    "software": "SCIENCES, TECHNOLOGIES, SANT",
    "fullstack": "SCIENCES, TECHNOLOGIES, SANT",
    "full-stack": "SCIENCES, TECHNOLOGIES, SANT",
    "backend": "SCIENCES, TECHNOLOGIES, SANT",
    "frontend": "SCIENCES, TECHNOLOGIES, SANT",
    "front-end": "SCIENCES, TECHNOLOGIES, SANT",
    "devops": "SCIENCES, TECHNOLOGIES, SANT",
    "sre": "SCIENCES, TECHNOLOGIES, SANT",
    "cloud": "SCIENCES, TECHNOLOGIES, SANT",
    "web": "SCIENCES, TECHNOLOGIES, SANT",
    "mobile": "SCIENCES, TECHNOLOGIES, SANT",
    "architecte": "SCIENCES, TECHNOLOGIES, SANT",
    "ingenieur": "SCIENCES, TECHNOLOGIES, SANT",
    "ingénieur": "SCIENCES, TECHNOLOGIES, SANT",
    # Data / ML
    "data": "SCIENCES, TECHNOLOGIES, SANT",
    "machine learning": "SCIENCES, TECHNOLOGIES, SANT",
    "deep learning": "SCIENCES, TECHNOLOGIES, SANT",
    "analyste": "SCIENCES, TECHNOLOGIES, SANT",
    "data scientist": "SCIENCES, TECHNOLOGIES, SANT",
    "data engineer": "SCIENCES, TECHNOLOGIES, SANT",
    "business intelligence": "SCIENCES, TECHNOLOGIES, SANT",
    "big data": "SCIENCES, TECHNOLOGIES, SANT",
    # Cybersécurité
    "cybersécurité": "SCIENCES, TECHNOLOGIES, SANT",
    "cybersecurite": "SCIENCES, TECHNOLOGIES, SANT",
    "sécurité": "SCIENCES, TECHNOLOGIES, SANT",
    "securite": "SCIENCES, TECHNOLOGIES, SANT",
    "pentest": "SCIENCES, TECHNOLOGIES, SANT",
    "audit": "SCIENCES, TECHNOLOGIES, SANT",
    # Design / UX
    "design": "SCIENCES HUMAINES ET SOCIALES",
    "ux": "SCIENCES HUMAINES ET SOCIALES",
    "ui": "SCIENCES HUMAINES ET SOCIALES",
    "graphiste": "SCIENCES HUMAINES ET SOCIALES",
    # Marketing / Communication
    "marketing": "SCIENCES HUMAINES ET SOCIALES",
    "communication": "SCIENCES HUMAINES ET SOCIALES",
    "digital": "SCIENCES HUMAINES ET SOCIALES",
    # Finance / Management
    "finance": "SCIENCES HUMAINES ET SOCIALES",
    "comptable": "SCIENCES HUMAINES ET SOCIALES",
    "gestion": "SCIENCES HUMAINES ET SOCIALES",
    "management": "SCIENCES HUMAINES ET SOCIALES",
    # Science / Recherche générale
    "biologie": "SCIENCES, TECHNOLOGIES, SANT",
    "chimie": "SCIENCES, TECHNOLOGIES, SANT",
    "physique": "SCIENCES, TECHNOLOGIES, SANT",
    "math": "SCIENCES, TECHNOLOGIES, SANT",
    "santé": "SCIENCES, TECHNOLOGIES, SANT",
    "medecine": "SCIENCES, TECHNOLOGIES, SANT",
    "médecine": "SCIENCES, TECHNOLOGIES, SANT",
}


def classify_domain(title: str, description: str = "") -> str | None:
    """Map job title + description to a Mon Master domain filter.

    Returns a domain substring suitable for ``LIKE '%X%'`` queries,
    or ``None`` if no match (search all domains).
    """
    combined = f"{title} {description}".lower()
    for keyword, domain in _DOMAIN_KEYWORDS.items():
        if keyword in combined:
            return domain
    return None
