import asyncio

from scripts.phase4_benchmark_compare import (
    run_benchmark,
    _build_compact_summary,
    _build_markdown_report,
    _build_findings_and_recommendations,
)


def _minimal_case(case_id: str, remote_stress: bool, strict_remote_validation: bool = False):
    constraints = {
        "scenario": "warm",
        "top_k": 2,
        "ground_truth_ids": ["b1"],
    }
    if remote_stress:
        constraints["remote_stress"] = True
    if strict_remote_validation:
        constraints["strict_remote_validation"] = True

    return {
        "case_id": case_id,
        "query": "Recommend science fiction books.",
        "user_profile": {"preferred_language": "en"},
        "history": [
            {
                "title": "Dune",
                "genres": ["science_fiction"],
                "rating": 5,
                "language": "en",
            }
        ],
        "books": [
            {
                "book_id": "b1",
                "title": "Foundation",
                "description": "Civilization science fiction.",
                "genres": ["science_fiction"],
            },
            {
                "book_id": "b2",
                "title": "Hyperion",
                "description": "Layered speculative narrative.",
                "genres": ["science_fiction"],
            },
        ],
        "constraints": constraints,
    }


def test_run_benchmark_remote_stress_generates_nonzero_fallback_rates():
    cases = [
        _minimal_case("normal_case", remote_stress=False),
        _minimal_case("stress_case", remote_stress=True),
    ]

    report = asyncio.run(run_benchmark(cases))
    methods = {row["method"]: row for row in report["methods"]}

    acps_summary = methods["acps_multi_agent"]["summary"]
    assert acps_summary["remote_attempt_rate"] > 0.0
    assert acps_summary["fallback_rate"] > 0.0
    assert report["reliability_dashboard"]["acps_reliability"]["fallback_mode"]["fallback_observed_rate"] > 0.0

    stress_run = next(row for row in methods["acps_multi_agent"]["runs"] if row["case_id"] == "stress_case")
    assert stress_run["remote_attempt_rate"] > 0.0
    assert stress_run["fallback_rate"] > 0.0

    assert methods["traditional_hybrid"]["summary"]["fallback_rate"] == 0.0
    assert methods["multi_agent_proxy"]["summary"]["fallback_rate"] == 0.0


def test_run_benchmark_remote_strict_stress_keeps_fallback_zero_for_strict_case():
    cases = [
        _minimal_case("normal_case", remote_stress=False),
        _minimal_case("strict_stress_case", remote_stress=True, strict_remote_validation=True),
    ]

    report = asyncio.run(run_benchmark(cases))
    methods = {row["method"]: row for row in report["methods"]}

    strict_run = next(row for row in methods["acps_multi_agent"]["runs"] if row["case_id"] == "strict_stress_case")
    assert strict_run["state"] == "needs_input"
    assert strict_run["remote_attempt_rate"] > 0.0
    assert strict_run["fallback_rate"] == 0.0
    assert strict_run["strict_failure"] == 1.0

    acps_summary = methods["acps_multi_agent"]["summary"]
    assert acps_summary["strict_failure_rate"] > 0.0
    assert report["reliability_dashboard"]["acps_reliability"]["strict_mode"]["failure_rate"] > 0.0


def test_build_compact_summary_contains_demo_fields():
    cases = [
        _minimal_case("normal_case", remote_stress=False),
        _minimal_case("strict_stress_case", remote_stress=True, strict_remote_validation=True),
    ]
    report = asyncio.run(run_benchmark(cases))
    summary = _build_compact_summary(report)

    assert summary["winner_method"] is not None
    assert "acps_quality" in summary
    assert "acps_efficiency" in summary
    assert "acps_reliability" in summary
    assert "strict_mode" in summary["acps_reliability"]
    assert "fallback_mode" in summary["acps_reliability"]


def test_build_markdown_report_contains_required_sections():
    cases = [
        _minimal_case("normal_case", remote_stress=False),
        _minimal_case("strict_stress_case", remote_stress=True, strict_remote_validation=True),
    ]
    report = asyncio.run(run_benchmark(cases))
    summary = _build_compact_summary(report)
    markdown = _build_markdown_report(report, summary)

    assert "# Phase IV Benchmark Report (Compact)" in markdown
    assert "## Run Summary" in markdown
    assert "## ACPs Quality" in markdown
    assert "## ACPs Efficiency" in markdown
    assert "## ACPs Reliability Dashboard" in markdown
    assert "### Strict Mode" in markdown
    assert "### Fallback Mode" in markdown
    assert "### Overall" in markdown
    assert "## Findings & Recommendations" in markdown
    assert "### Findings" in markdown
    assert "### Recommendations" in markdown
    assert "Winner method:" in markdown


def test_findings_and_recommendations_rules_produce_outputs():
    summary = {
        "acps_quality": {"ndcg_at_k": 0.65},
        "acps_efficiency": {"latency_ms_mean": 9000.0},
        "acps_reliability": {
            "overall": {
                "fallback_rate": 0.3,
                "strict_failure_rate": 0.2,
                "remote_success_rate": 0.1,
            }
        },
    }
    result = _build_findings_and_recommendations(summary)
    assert len(result["findings"]) >= 4
    assert len(result["recommendations"]) >= 3
