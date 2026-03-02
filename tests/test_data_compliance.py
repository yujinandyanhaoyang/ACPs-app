from pathlib import Path

from scripts.check_data_compliance import run_check


def test_data_compliance_check_passes_for_current_license_doc():
    ok, issues = run_check()
    assert ok is True
    assert issues == []


def test_data_compliance_requires_strict_traceability_records(tmp_path):
    sample = tmp_path / "data-license.md"
    sample.write_text(
        """
# Data License & Compliance Baseline

## Approved List (Current)
### Chinese
- Douban source approved.
### English
- Open Library source approved.

## Approved Source Records
| source | dataset_id | language | url | acquired_at_utc | sha256 | status | local_path |
|---|---|---|---|---|---|---|---|
| douban | d1 | zh | invalid-url | 2026-03-01 00:00:00 | bad-hash | approved | |
| openlibrary | e1 | en | https://openlibrary.org/developers/dumps | 2026-03-01T00:20:00Z | fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210 | approved | data/raw/openlibrary/books_en.jsonl |

## Fallback List
- fallback

## CI Compliance Checklist
- [ ] checklist
""".strip(),
        encoding="utf-8",
    )

    ok, issues = run_check(sample)
    assert ok is False
    assert any("invalid url" in issue for issue in issues)
    assert any("invalid acquired_at_utc" in issue for issue in issues)
    assert any("invalid sha256" in issue for issue in issues)
    assert any("missing local_path" in issue for issue in issues)
