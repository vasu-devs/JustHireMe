from pydantic import BaseModel, Field


class S(BaseModel):
    n:   str
    cat: str = "general"


class E(BaseModel):
    role:   str
    co:     str
    period: str
    d:      str
    s:      list[str] = Field(default_factory=list)


class P(BaseModel):
    title:  str
    stack:  list[str]       = Field(default_factory=list)
    repo:   str | None   = None
    impact: str             = ""
    s:      list[str]       = Field(default_factory=list)


class C(BaseModel):
    n:        str
    s:        str      = ""
    skills:   list[S]  = Field(default_factory=list)
    exp:      list[E]  = Field(default_factory=list)
    projects: list[P]  = Field(default_factory=list)
    certifications: list[str] = Field(default_factory=list)
    education:      list[str] = Field(default_factory=list)
    achievements:   list[str] = Field(default_factory=list)
