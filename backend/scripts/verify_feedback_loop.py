#!/usr/bin/env python
"""Prove the feedback loop actually moves scores, with real before/after numbers
-- not just "the code exists so it must work".

Runs entirely against a THROWAWAY COPY of the real database (never the live
crm.db the desktop app / job_loop.py use), because this deliberately writes a
SIMULATED outcome ("interview" / "app_rejected" on a real lead that did not
really happen) purely to measure the ranking effect.

What it measures, end to end:
  1. Snapshot every open lead's (score, signal_score).
  2. Record a simulated "interview" outcome on one real, already-scored lead
     (scripts/review.py's own code path: save_lead_feedback + the SAME
     RankingService.recompute_feedback_signals() review.py calls after every
     `mark` -- not a reimplementation of the feedback loop, a call into it).
  3. Snapshot again; report the biggest positive movers.
  4. Record a simulated "app_rejected" outcome on a second lead, recompute
     again, and report the biggest negative movers.

If the deltas are all zero, this prints that plainly -- it does not spin the
result as "the mechanism exists" when the mechanism didn't move anything.

    python scripts/verify_feedback_loop.py
    python scripts/verify_feedback_loop.py --keep-scratch   # don't delete the copy after
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

_REAL_APP_DATA = Path.home() / "AppData" / "Roaming" / "com.vasudev-siddh.justhireme"
# This session's scratch dir if it still exists; the system temp dir otherwise
# (this script outlives any one session, so it can't depend on that path).
_CLAUDE_SCRATCH = Path(
    r"C:\Users\VASUDE~1\AppData\Local\Temp\claude\e--STUDY-Projects--Active-JustHireMe"
    r"\c4d74354-30b5-4be3-b87d-05f355d12bb7\scratchpad"
)
_SCRATCH_PARENT = _CLAUDE_SCRATCH if _CLAUDE_SCRATCH.is_dir() else Path(tempfile.gettempdir())


def _make_scratch_copy() -> Path:
    """Copy the real crm.db into a fresh scratch dir and point EVERY backend
    module that resolves its DB path from app_data_dir() (data.sqlite.*,
    ranking.service's Repository, ...) at that copy instead -- this MUST run
    before any of those modules are imported, since several of them bind
    their default db_path at import time (see job_loop.py's identical
    comment). Nothing this script does can therefore touch the real DB."""
    if not _REAL_APP_DATA.joinpath("crm.db").exists():
        raise SystemExit(f"real crm.db not found under {_REAL_APP_DATA}")
    scratch_dir = Path(tempfile.mkdtemp(prefix="jhm_feedback_scratch_", dir=str(_SCRATCH_PARENT)))
    shutil.copy2(_REAL_APP_DATA / "crm.db", scratch_dir / "crm.db")

    # Link (never copy) the ~87MB ONNX embedding model dir in read-only, so the
    # semantic half of the feedback loop (feedback_semantic.preference_deltas)
    # runs with REAL embeddings here too, instead of silently falling back to
    # the hash embedder (which always returns a zero delta) just because a
    # fresh scratch app-data dir has no downloaded model.
    real_models = _REAL_APP_DATA / "models"
    if real_models.exists():
        link = scratch_dir / "models"
        try:
            subprocess.run(
                ["cmd", "/c", "mklink", "/J", str(link), str(real_models)],
                capture_output=True, text=True, check=True,
            )
        except Exception:
            shutil.copytree(real_models, link)

    os.environ["JHM_APP_DATA_DIR"] = str(scratch_dir)
    return scratch_dir / "crm.db"


def _cleanup_scratch(scratch_dir: Path) -> None:
    """Remove the scratch dir WITHOUT ever touching the real models cache.

    ``models`` may be a junction pointing at the real ~87MB ONNX model dir --
    unlink the junction itself first (os.rmdir on a junction removes only the
    reparse point, never the target's contents) before shutil.rmtree'ing the
    rest, so an rmtree that ever started following the junction could not
    delete the user's real model cache. If linking fell back to a real
    copytree instead (non-junction), rmdir raises (dir not empty) and rmtree
    below just deletes that independent copy as normal.
    """
    models_link = scratch_dir / "models"
    if models_link.exists():
        try:
            os.rmdir(models_link)
        except OSError:
            pass
    shutil.rmtree(scratch_dir, ignore_errors=True)


_SCRATCH_DB = _make_scratch_copy()

from data.sqlite.leads import get_all_leads, save_lead_feedback  # noqa: E402
from ranking.service import RankingService  # noqa: E402


def _snapshot(db_path: str) -> dict[str, tuple[int, int]]:
    return {
        lead["job_id"]: (int(lead.get("score") or 0), int(lead.get("signal_score") or 0))
        for lead in get_all_leads(db_path)
    }


def _pick_anchor(leads: list[dict], *, min_score: int, exclude: set[str]) -> dict | None:
    candidates = [
        lead for lead in leads
        if lead["job_id"] not in exclude
        and int(lead.get("score") or 0) >= min_score
        and str(lead.get("feedback") or "") == ""
        and (lead.get("description") or lead.get("title"))
    ]
    candidates.sort(key=lambda lead: -int(lead.get("score") or 0))
    return candidates[0] if candidates else None


def _split_axis(before: dict, after: dict, idx: int) -> tuple[list, list]:
    """(movers_up, movers_down) for one axis (0=score, 1=signal_score) as
    (job_id, before, after, delta) rows, each already sorted by |delta| desc."""
    up, down = [], []
    for job_id, after_vals in after.items():
        before_vals = before.get(job_id, after_vals)
        b, a = before_vals[idx], after_vals[idx]
        d = a - b
        if d > 0:
            up.append((job_id, b, a, d))
        elif d < 0:
            down.append((job_id, b, a, d))
    up.sort(key=lambda row: row[3], reverse=True)
    down.sort(key=lambda row: row[3])
    return up, down


def _print_rows(rows: list, lead_by_id: dict, top: int) -> None:
    for job_id, b, a, d in rows[:top]:
        lead = lead_by_id.get(job_id, {})
        print(f"      {b:>3} -> {a:>3}  ({d:+d})  {str(lead.get('title') or '?')[:50]:<50} @ {str(lead.get('company') or '?')[:20]}")


def _report_movers(
    label: str, before: dict, after: dict, lead_by_id: dict, *, top: int = 5, direction: str = "up",
) -> tuple[list, list]:
    """Two independent axes move independently: ``score`` (the MATCH score,
    shifted by feedback_semantic's embedding-similarity model) and
    ``signal_score`` (posting-quality/freshness, shifted by feedback_ranker's
    metadata-overlap model -- platform/company/stack/tag). Reported
    separately since a zero on one axis does not imply a zero on the other.
    Shows the movers in the EXPECTED direction explicitly (never dresses up
    "0 moved up" by displaying the least-bad negative mover instead)."""
    score_up, score_down = _split_axis(before, after, 0)
    sig_up, sig_down = _split_axis(before, after, 1)
    score_shown, sig_shown = (score_up, sig_up) if direction == "up" else (score_down, sig_down)

    print(f"\n  {label}")
    print(f"    match score (semantic):  {len(score_up)} moved up, {len(score_down)} moved down")
    _print_rows(score_shown, lead_by_id, top)
    print(f"    signal score (metadata: platform/company/stack/tag):  {len(sig_up)} moved up, {len(sig_down)} moved down")
    _print_rows(sig_shown, lead_by_id, top)
    return score_shown, sig_shown


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--keep-scratch", action="store_true", help="don't delete the scratch DB copy afterward")
    parser.add_argument("--min-score", type=int, default=60, help="minimum score for a lead to qualify as an outcome anchor")
    args = parser.parse_args()

    db_path = str(_SCRATCH_DB)
    print(f"  scratch DB (real crm.db is NEVER touched): {db_path}")

    leads = get_all_leads(db_path)
    lead_by_id = {lead["job_id"]: lead for lead in leads}
    print(f"  {len(leads)} leads loaded")

    # This is a COPY of the real, in-use database -- it already carries
    # whatever real feedback the founder has recorded using the app (43
    # "incorrect_category" tags at copy time). recompute_feedback_signals()
    # rebuilds its preference model from ALL feedback rows every call, not
    # incrementally, so measuring "before vs. after adding ONE new outcome"
    # requires a baseline recompute FIRST (absorbing whatever pre-existing
    # feedback + embedding state already exists) -- otherwise the diff would
    # conflate "effect of my one simulated outcome" with "effect of every
    # real feedback label recorded before this script ever ran".
    print("\n  baseline pass (absorbs pre-existing real feedback before any simulated outcome)")
    asyncio.run(RankingService().recompute_feedback_signals())
    before1 = _snapshot(db_path)

    anchor_up = _pick_anchor(leads, min_score=args.min_score, exclude=set())
    if not anchor_up:
        print(f"  ! no lead scored >= {args.min_score} to use as the 'interview' anchor -- lower --min-score")
        return 1
    print(f"\n  [1] simulating outcome=interview on: {anchor_up['title'][:60]!r} @ {anchor_up['company']} "
          f"(score={anchor_up.get('score')}, job_id={anchor_up['job_id'][:10]})")
    save_lead_feedback(anchor_up["job_id"], "interview", note="[SIMULATED for verify_feedback_loop.py]", db_path=db_path)
    changed_up = asyncio.run(RankingService().recompute_feedback_signals())
    print(f"  recompute_feedback_signals(): {len(changed_up)} lead(s) touched")

    after1 = _snapshot(db_path)
    up_score, up_sig = _report_movers("Movers UP after the 'interview' outcome", before1, after1, lead_by_id, direction="up")

    # Second outcome, layered on top of the first (recompute is idempotent per
    # lead, so this measures the REJECTION's own effect, not a reset).
    before2 = after1
    anchor_down = _pick_anchor(leads, min_score=args.min_score, exclude={anchor_up["job_id"]})
    if not anchor_down:
        print(f"  ! no second lead scored >= {args.min_score} to use as the 'app_rejected' anchor")
        return 1
    print(f"\n  [2] simulating outcome=app_rejected on: {anchor_down['title'][:60]!r} @ {anchor_down['company']} "
          f"(score={anchor_down.get('score')}, job_id={anchor_down['job_id'][:10]})")
    save_lead_feedback(anchor_down["job_id"], "app_rejected", note="[SIMULATED for verify_feedback_loop.py]", db_path=db_path)
    changed_down = asyncio.run(RankingService().recompute_feedback_signals())
    print(f"  recompute_feedback_signals(): {len(changed_down)} lead(s) touched")

    after2 = _snapshot(db_path)
    down_score, down_sig = _report_movers("Movers DOWN after the 'app_rejected' outcome", before2, after2, lead_by_id, direction="down")

    print()
    if not any((up_score, up_sig, down_score, down_sig)):
        print("  RESULT: zero effect -- neither simulated outcome moved any other lead on either axis.")
    else:
        print(
            f"  RESULT: interview outcome moved {len(up_score)} lead(s) on match score / {len(up_sig)} on signal score; "
            f"app_rejected outcome moved {len(down_score)} lead(s) on match score / {len(down_sig)} on signal score. "
            f"See deltas above."
        )

    if not args.keep_scratch:
        # data.sqlite.connection pools one open sqlite3 handle per thread+path
        # and only releases it on close_all() -- without this, the scratch
        # crm.db stays open (Windows won't delete an open file) and rmtree
        # silently leaves it behind despite "removed" being printed.
        from data.sqlite.connection import close_all

        close_all()
        _cleanup_scratch(Path(db_path).parent)
        removed = not Path(db_path).exists()
        print(f"\n  scratch copy {'removed' if removed else 'FAILED TO REMOVE'} ({Path(db_path).parent})")
    else:
        print(f"\n  scratch copy kept at {Path(db_path).parent}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
