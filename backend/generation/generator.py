from __future__ import annotations

import sys

from generation.generators import package as _module
from generation.generators.package import (
    _DocPackage,
    _assets,
    _clean,
    _normalize_package,
    _render,
    _render_resume_template,
    _strip_inline,
    get_profile,
    run,
    run_package,
)

sys.modules[__name__] = _module

__all__ = [
    "_DocPackage",
    "_assets",
    "_clean",
    "_normalize_package",
    "_render",
    "_render_resume_template",
    "_strip_inline",
    "get_profile",
    "run",
    "run_package",
]
