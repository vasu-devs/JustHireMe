from pydantic import BaseModel, Field


class S(BaseModel):
    n:   str
    cat: str = "general"


class E(BaseModel):
    role:   str
    co:     str
    period: str
    d:      str
    # Per-role location ("Mountain View, CA"). Resumes routinely carry this on
    # the experience header; dropping it lost real information on import (#111).
    location: str = ""
    s:      list[str] = Field(default_factory=list)


class P(BaseModel):
    title:  str
    stack:  list[str]       = Field(default_factory=list)
    repo:   str | None   = None
    impact: str             = ""
    s:      list[str]       = Field(default_factory=list)


class C(BaseModel):
    # Defaulted (not required) so an empty LLM fallback is still a valid model;
    # the deterministic parser / merge fills in the real name when the LLM is
    # unavailable. A required field here crashes downstream `.n` access.
    n:        str      = ""
    s:        str      = ""
    # Free-text location from the CV (city/region/country), used to target
    # discovery to the candidate's region. Optional and field-agnostic.
    loc:      str      = ""
    skills:   list[S]  = Field(default_factory=list)
    exp:      list[E]  = Field(default_factory=list)
    projects: list[P]  = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    education:      list[str] = Field(default_factory=list)
    achievements:   list[str] = Field(default_factory=list)
