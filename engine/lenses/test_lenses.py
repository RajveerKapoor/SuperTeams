#!/usr/bin/env python3
"""test_lenses.py — the Curiosity Protocol battery (doctrine/12 stage 5).

The three properties that make the protocol trustworthy, each tested as a
property of the machinery rather than a habit of whoever is using it:

  record ALL      — every artifact enters the pool, including the boring ones
  never pre-gate  — no artifact carries a status that excludes it from the
                    later assessment; pre-judgment goes in `provenance`
  promote later   — BH across the WHOLE pool, in a separate pass, never in-wave

    pytest lenses/test_lenses.py -q
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ENGINE = Path(__file__).resolve().parent.parent
RUNNERS = ENGINE / "runners"
sys.path.insert(0, str(ENGINE))

from lenses import (  # noqa: E402
    LENS_STATUS,
    Candidate,
    available,
    benjamini_hochberg,
    bh_q_values,
    get_lens,
    sweep_pool,
)


def record(artifact_id: str, **kwargs) -> dict:
    """A pool line with the schema's defaults filled in."""
    base = {
        "artifact_id": artifact_id,
        "value": None,
        "kind": "measurement",
        "context": None,
        "source_task": "TASK_0001",
        "source_wave": "2k",
        "lens": "generic",
        "provenance": "real",
        "promotion_status": "LOGGED",
        "candidate_note": None,
        "p_value": None,
        "fdr_q": None,
        "reverify_recipe": None,
        "path": None,
        "sha256": None,
        "ts_iso": "2026-08-15T00:00:00Z",
    }
    base.update(kwargs)
    return base


def run(workspace: Path, script: str, *args: str) -> subprocess.CompletedProcess:
    env = dict(os.environ, SUPERTEAM_WORKSPACE=str(workspace))
    return subprocess.run(
        [sys.executable, str(RUNNERS / script), *args],
        capture_output=True, text=True, env=env, timeout=120,
    )


# ---------------------------------------------------------------------------
# The registry of lenses
# ---------------------------------------------------------------------------


def test_all_five_lenses_are_registered():
    assert set(available()) == {"research", "engineering", "ops", "writing", "generic"}


def test_an_unknown_lens_falls_back_to_generic():
    """A typo'd lens name must not create a silent hole in the pool. Generic
    pre-judges nothing, so falling back is conservative in the right direction."""
    assert get_lens("reserch").name == "generic"
    assert get_lens(None).name == "generic"
    assert get_lens("").name == "generic"


def test_no_lens_can_promote():
    """A lens may only FLAG. Promotion is a later pass over the whole pool — a
    finding promoted by the pass that found it has been graded by its author."""
    assert LENS_STATUS == "FLAGGED"
    for name in available():
        source = (ENGINE / "lenses" / f"{name}.py").read_text(encoding="utf-8")
        assert "PROMOTED" not in source, f"{name} lens references PROMOTED"


# ---------------------------------------------------------------------------
# The lenses themselves
# ---------------------------------------------------------------------------


def test_research_lens_matches_a_known_constant():
    found = get_lens("research").sweep([record("ART_0001", value=3.14159265)])
    reasons = " ".join(c.reason for c in found)
    assert "π" in reasons
    assert any(c.p_value is not None for c in found)


def test_research_lens_matches_a_small_rational():
    found = get_lens("research").sweep([record("ART_0001", value=0.75)])
    assert any("3/4" in c.reason for c in found)


def test_research_lens_finds_a_ratio_between_two_artifacts():
    found = get_lens("research").sweep([
        record("ART_0001", value=6.28318530),
        record("ART_0002", value=2.0),
    ])
    assert any("ratio" in c.reason and "π" in c.reason for c in found)


def test_unremarkable_numbers_get_p_values_that_do_not_survive_fdr():
    """The protocol pre-gates nothing, so an unremarkable number may still raise
    a candidate — but its p-value must be honest enough that BH discards it.

    41.902 sits within 5.7e-5 of 419/10. At relative precision that looks
    striking; in truth almost ANY number near 42 is that close to some rational
    with a small denominator, because a relative window covers more of the
    rational grid the larger the value is. The null has to know that, or the
    pool fills with arithmetic dressed up as discovery.
    """
    found = get_lens("research").sweep([
        record("ART_0001", value=8.317246189234),
        record("ART_0002", value=41.9023874651),
    ])
    scored = [c.p_value for c in found if c.p_value is not None]
    assert not any(benjamini_hochberg(scored, 0.10)), [
        (c.reason, c.p_value) for c in found if c.p_value is not None
    ]


def test_the_same_closeness_is_rarer_at_a_small_magnitude():
    """The magnitude term must actually discriminate, not just soften everything."""
    from curiosity.constants import p_rational_match

    near_one = p_rational_match(5.7e-5, magnitude=0.75)
    near_forty = p_rational_match(5.7e-5, magnitude=41.9)
    assert near_one < near_forty / 10


def test_research_lens_reports_a_truncated_sweep_instead_of_hiding_it():
    """No silent caps. A bounded sweep must say so, in the pool itself."""
    lens = get_lens("research")
    lens.max_pairs = 5
    records = [record(f"ART_{i:04d}", value=100.0 + i * 7.31) for i in range(20)]
    found = lens.sweep(records)
    assert any(
        c.kind == "infeasibility" and "TRUNCATED" in c.reason for c in found
    ), "a truncated pairwise sweep did not declare itself"


def test_engineering_lens_flags_a_flaky_test():
    found = get_lens("engineering").sweep([
        record("ART_0001", lens="engineering",
               context="suite passes on retry, intermittent failure in auth_test")
    ])
    assert any("flaky" in c.reason for c in found)


def test_engineering_lens_flags_a_perf_cliff_from_the_numbers_alone():
    """No keyword needed: 40x the median across comparable measurements."""
    records = [record(f"ART_{i:04d}", lens="engineering", value=1.0 + i * 0.01)
               for i in range(9)]
    records.append(record("ART_0099", lens="engineering", value=40.0))
    found = get_lens("engineering").sweep(records)
    assert any(c.artifact_id == "ART_0099" and "median" in c.reason for c in found)


def test_engineering_lens_flags_a_hidden_gap():
    found = get_lens("engineering").sweep([
        record("ART_0001", lens="engineering", context="TODO: handle the null case")
    ])
    assert any("hidden-gap" in c.reason for c in found)


def test_ops_lens_flags_an_out_of_band_metric():
    records = [record(f"ART_{i:04d}", lens="ops", value=100.0 + i) for i in range(10)]
    records.append(record("ART_0099", lens="ops", value=100000.0))
    found = get_lens("ops").sweep(records)
    assert any(c.artifact_id == "ART_0099" for c in found)


def test_ops_lens_flags_monotone_creep():
    """Something that only goes up is a leak until proven otherwise."""
    records = [record(f"ART_{i:04d}", lens="ops", value=100.0 * (1.4**i)) for i in range(8)]
    found = get_lens("ops").sweep(records)
    assert any(c.kind == "scaling" and "monotonic" in c.reason for c in found)


def test_writing_lens_flags_a_claim_that_outran_its_evidence():
    found = get_lens("writing").sweep([
        record("ART_0001", lens="writing",
               context="this proves the approach always works in all cases")
    ])
    assert any("outran-evidence" in c.reason for c in found)


def test_writing_lens_flags_an_artifact_with_no_context():
    found = get_lens("writing").sweep([
        record("ART_0001", lens="writing", path="drafts/chapter1.md", context=None)
    ])
    assert any("no context line" in c.reason for c in found)


def test_generic_lens_has_no_keyword_table():
    """Gravity and calculus were not matches against an existing library. A lens
    that filters through 'does this match something I already know?' can only
    ever rediscover, so the generic one must carry no such prior."""
    source = (ENGINE / "lenses" / "generic.py").read_text(encoding="utf-8")
    assert "re.compile" not in source
    assert "SIGNALS" not in source


def test_generic_lens_respects_the_authors_own_flag():
    """The Subagent that produced an artifact had context nobody downstream has."""
    found = get_lens("generic").sweep([
        record("ART_0001", candidate_note="the residual went the wrong way and I cannot say why")
    ])
    assert any("flagged by the work that produced it" in c.reason for c in found)


def test_generic_lens_notices_identical_repeats():
    records = [record(f"ART_{i:04d}", value=7.5) for i in range(4)]
    found = get_lens("generic").sweep(records)
    assert any("identical value" in c.reason for c in found)


def test_sweep_pool_routes_each_record_to_its_own_lens():
    found = sweep_pool([
        record("ART_0001", lens="research", value=3.14159265),
        record("ART_0002", lens="writing", context="obviously this is correct"),
    ])
    ids = {c.artifact_id for c in found}
    assert {"ART_0001", "ART_0002"} <= ids


# ---------------------------------------------------------------------------
# Multiple-comparison discipline
# ---------------------------------------------------------------------------


def test_bh_is_a_step_up_not_a_per_rank_test():
    """p=[0.001, 0.03] at q=0.05, n=2: rank 2 passes (0.03 ≤ 0.05), so the
    step-up rejects BOTH — including rank 1, which its own threshold (0.025)
    would have failed. Testing each p independently is the classic wrong version.
    """
    assert benjamini_hochberg([0.001, 0.03], 0.05) == [True, True]


def test_bh_rejects_nothing_when_nothing_is_significant():
    assert benjamini_hochberg([0.4, 0.6, 0.9], 0.10) == [False, False, False]


def test_bh_handles_an_empty_pool():
    assert benjamini_hochberg([], 0.10) == []
    assert bh_q_values([]) == []


def test_q_values_are_monotone_in_p():
    p_values = [0.001, 0.008, 0.02, 0.3, 0.7, 0.9]
    q_values = bh_q_values(p_values)
    pairs = sorted(zip(p_values, q_values))
    assert all(a[1] <= b[1] + 1e-12 for a, b in zip(pairs, pairs[1:]))


def test_a_large_pool_of_noise_promotes_nothing():
    """The property the whole 'promote later, over the whole pool' rule exists
    for: 1000 uniform p-values contain ~50 below 0.05 by arithmetic alone. Each
    would look convincing alone. BH must promote none of them."""
    p_values = [(i + 0.5) / 1000 for i in range(1000)]
    assert not any(benjamini_hochberg(p_values, 0.10))


# ---------------------------------------------------------------------------
# The harvest: record-all, no pre-gating, promote-later
# ---------------------------------------------------------------------------


@pytest.fixture()
def mission(tmp_path: Path) -> Path:
    ws = tmp_path / "mission"
    subprocess.run(
        [sys.executable, str(RUNNERS / "init_workspace.py"), str(ws),
         "--mission", "lens-test", "--mode", "finite"],
        capture_output=True, text=True, timeout=120, check=True,
    )
    run(ws, "roadmap.py", "add-task", "--title", "produce artifacts", "--lens", "research")
    run(ws, "pre_register.py", "--set", "--disc", "TASK_0001",
        "--dod", "artifacts exist", "--check", "artifacts.jsonl grows",
        "--precision", "deterministic", "--target-n", "1")
    run(ws, "pre_register.py", "--freeze")
    return ws


def test_log_artifact_records_everything_as_logged_and_unpromoted(mission: Path):
    """Record ALL: even the boring artifact enters the pool, at LOGGED."""
    for index, value in enumerate([3.14159265, 999.123456789, 0.5]):
        path = mission / "reports" / f"m{index}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"value {value}\n", encoding="utf-8")
        result = run(mission, "log_artifact.py", "--task", "TASK_0001",
                     "--path", f"reports/m{index}.md", "--kind", "measurement",
                     "--lens", "research", "--value", str(value),
                     "--context", "a boring-looking measurement")
        assert result.returncode == 0, result.stderr

    lines = [json.loads(line) for line in
             (mission / "artifacts.jsonl").read_text().splitlines() if line.strip()]
    assert len(lines) == 3
    assert all(line["promotion_status"] == "LOGGED" for line in lines)
    assert all(line["fdr_q"] is None for line in lines)


def test_provenance_carries_pre_judgment_not_status(mission: Path):
    """A canary value is TAGGED as synthetic, but still enters the pool at LOGGED.
    Using a status to express 'this one does not count' is what would exclude it
    from later assessment — the exact rule the predecessor set after nearly
    pre-gating away foundational null results."""
    path = mission / "reports" / "canary.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("canary\n", encoding="utf-8")
    run(mission, "log_artifact.py", "--task", "TASK_0001",
        "--path", "reports/canary.md", "--kind", "measurement",
        "--lens", "research", "--provenance", "canary", "--value", "3.14159265")

    line = json.loads((mission / "artifacts.jsonl").read_text().splitlines()[-1])
    assert line["provenance"] == "canary"
    assert line["promotion_status"] == "LOGGED"


def test_harvest_dry_run_writes_nothing(mission: Path):
    path = mission / "reports" / "m.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n", encoding="utf-8")
    run(mission, "log_artifact.py", "--task", "TASK_0001", "--path", "reports/m.md",
        "--kind", "measurement", "--lens", "research", "--value", "3.14159265")

    before = (mission / "artifacts.jsonl").read_text()
    result = run(mission, "harvest.py", "--dry-run")
    assert result.returncode == 0, result.stderr
    assert (mission / "artifacts.jsonl").read_text() == before


def test_harvest_promotes_and_stamps_a_q_value(mission: Path):
    """A single strong constant match in a small pool survives BH and is stamped."""
    path = mission / "reports" / "pi.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("pi\n", encoding="utf-8")
    run(mission, "log_artifact.py", "--task", "TASK_0001", "--path", "reports/pi.md",
        "--kind", "measurement", "--lens", "research", "--value", "3.14159265")

    result = run(mission, "harvest.py", "--apply", "--q", "0.10")
    assert result.returncode == 0, result.stderr

    line = json.loads((mission / "artifacts.jsonl").read_text().splitlines()[-1])
    assert line["promotion_status"] == "PROMOTED"
    assert line["fdr_q"] is not None
    assert line["candidate_note"]


def test_harvest_leaves_unswept_artifacts_logged_not_rejected(mission: Path):
    """An artifact no lens fired on is not a negative result. Marking it REJECTED
    would quietly remove it from every future harvest."""
    path = mission / "reports" / "dull.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("dull\n", encoding="utf-8")
    run(mission, "log_artifact.py", "--task", "TASK_0001", "--path", "reports/dull.md",
        "--kind", "measurement", "--lens", "research", "--value", "8.317246189234")

    run(mission, "harvest.py", "--apply")
    line = json.loads((mission / "artifacts.jsonl").read_text().splitlines()[-1])
    assert line["promotion_status"] == "LOGGED"


def test_no_pregating_check_passes_on_a_clean_pool(mission: Path):
    path = mission / "reports" / "m.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n", encoding="utf-8")
    run(mission, "log_artifact.py", "--task", "TASK_0001", "--path", "reports/m.md",
        "--kind", "measurement", "--lens", "research", "--value", "1.234")

    result = run(mission, "harvest.py", "--check-no-pregating")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "clean" in result.stdout


def test_no_pregating_check_catches_a_promotion_that_skipped_the_gate(mission: Path):
    """Someone hand-marks PROMOTED without a q-value: that finding never faced
    the multiple-comparison gate, and the check must say so."""
    path = mission / "reports" / "m.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n", encoding="utf-8")
    run(mission, "log_artifact.py", "--task", "TASK_0001", "--path", "reports/m.md",
        "--kind", "measurement", "--lens", "research", "--value", "1.234")

    pool = mission / "artifacts.jsonl"
    line = json.loads(pool.read_text().splitlines()[-1])
    line["promotion_status"] = "PROMOTED"
    pool.write_text(json.dumps(line) + "\n", encoding="utf-8")

    result = run(mission, "harvest.py", "--check-no-pregating")
    assert result.returncode != 0
    assert "never faced" in result.stdout


def test_no_pregating_check_catches_a_rejection_that_skipped_the_gate(mission: Path):
    path = mission / "reports" / "m.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x\n", encoding="utf-8")
    run(mission, "log_artifact.py", "--task", "TASK_0001", "--path", "reports/m.md",
        "--kind", "measurement", "--lens", "research", "--value", "1.234")

    pool = mission / "artifacts.jsonl"
    line = json.loads(pool.read_text().splitlines()[-1])
    line["promotion_status"] = "REJECTED"
    pool.write_text(json.dumps(line) + "\n", encoding="utf-8")

    result = run(mission, "harvest.py", "--check-no-pregating")
    assert result.returncode != 0
    assert "excluded from later assessment" in result.stdout
