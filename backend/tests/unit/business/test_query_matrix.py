from __future__ import annotations

from catalog.query_matrix import WORKDAY_EARLY_CAREER_QUERIES, expand_early_career_targets
from catalog.source_registry import SourceTarget


def _target(provider: str, scan_target: str) -> SourceTarget:
    return SourceTarget(
        target_id=f"{provider}:acme",
        company_id="company:acme",
        provider=provider,
        scan_target=scan_target,
    )


def test_workday_expands_to_bounded_early_career_queries() -> None:
    targets = expand_early_career_targets(
        [_target("workday", "ats:workday:acme:wd5:External:engineer")]
    )
    assert len(targets) == len(WORKDAY_EARLY_CAREER_QUERIES)
    assert {target.scan_target.rsplit(":", 1)[-1] for target in targets} == set(WORKDAY_EARLY_CAREER_QUERIES)
    assert len({target.target_id for target in targets}) == len(targets)


def test_full_board_provider_is_not_multiplied() -> None:
    target = _target("greenhouse", "ats:greenhouse:acme")
    assert expand_early_career_targets([target]) == [target]
