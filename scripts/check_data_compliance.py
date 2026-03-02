from __future__ import annotations

import re
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
LICENSE_PATH = PROJECT_ROOT / "docs" / "data-license.md"


_RECORD_LINE = re.compile(r"^\|(?P<body>.+)\|\s*$")
_UTC_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
_SHA256_PATTERN = re.compile(r"^[a-fA-F0-9]{64}$")


def _parse_source_records(text: str) -> list[dict[str, str]]:
    start = text.find("## Approved Source Records")
    if start < 0:
        return []

    tail = text[start:].splitlines()
    records: list[dict[str, str]] = []
    for line in tail:
        stripped = line.strip()
        if not stripped.startswith("|"):
            continue
        if "dataset_id" in stripped.lower():
            continue
        if stripped.startswith("|---"):
            continue
        match = _RECORD_LINE.match(stripped)
        if not match:
            continue
        cells = [cell.strip() for cell in match.group("body").split("|")]
        if len(cells) < 8:
            continue
        records.append(
            {
                "source": cells[0],
                "dataset_id": cells[1],
                "language": cells[2].lower(),
                "url": cells[3],
                "acquired_at_utc": cells[4],
                "sha256": cells[5],
                "status": cells[6].lower(),
                "local_path": cells[7],
            }
        )
    return records


def _validate_record(record: dict[str, str]) -> list[str]:
    issues: list[str] = []
    source = record.get("source", "")
    dataset_id = record.get("dataset_id", "")
    prefix = f"record[{source}:{dataset_id}]"

    url = record.get("url", "")
    if not (url.startswith("http://") or url.startswith("https://")):
        issues.append(f"{prefix} invalid url")

    acquired_at_utc = record.get("acquired_at_utc", "")
    if not _UTC_PATTERN.fullmatch(acquired_at_utc):
        issues.append(f"{prefix} invalid acquired_at_utc")

    sha256 = record.get("sha256", "")
    if not _SHA256_PATTERN.fullmatch(sha256):
        issues.append(f"{prefix} invalid sha256")

    local_path = record.get("local_path", "")
    if not local_path:
        issues.append(f"{prefix} missing local_path")

    return issues


def run_check(license_path: Path | None = None) -> tuple[bool, list[str]]:
    issues: list[str] = []
    path = license_path or LICENSE_PATH
    if not path.exists():
        return False, [f"missing file: {path}"]

    text = path.read_text(encoding="utf-8")

    required_snippets = [
        "## Approved List (Current)",
        "### Chinese",
        "### English",
        "## Approved Source Records",
        "## Fallback List",
        "## CI Compliance Checklist",
    ]
    for snippet in required_snippets:
        if snippet not in text:
            issues.append(f"missing required section: {snippet}")

    records = _parse_source_records(text)
    if not records:
        issues.append("no approved source records found")
        return False, issues

    record_issues: list[str] = []
    approved_zh = False
    approved_en = False
    approved_source_names = {"douban", "open library", "openlibrary", "modelscope", "goodreads"}
    has_recognizable_chinese = False
    has_recognizable_english = False
    for record in records:
        record_issues.extend(_validate_record(record))
        source = record.get("source", "").strip().lower()
        status = record.get("status", "")
        language = record.get("language", "")

        if source in approved_source_names and language in {"zh", "mixed", "zh/en"}:
            has_recognizable_chinese = True
        if source in approved_source_names and language in {"en", "mixed", "zh/en"}:
            has_recognizable_english = True

        if status == "approved" and language in {"zh", "mixed", "zh/en"}:
            approved_zh = True
        if status == "approved" and language in {"en", "mixed", "zh/en"}:
            approved_en = True

    issues.extend(record_issues)
    if not has_recognizable_chinese:
        issues.append("no recognizable approved Chinese source found")
    if not has_recognizable_english:
        issues.append("no recognizable approved English source found")
    if not approved_zh:
        issues.append("no approved zh/mixed source record")
    if not approved_en:
        issues.append("no approved en/mixed source record")

    return len(issues) == 0, issues


def main() -> int:
    ok, issues = run_check()
    if ok:
        print("DATA_COMPLIANCE_CHECK: PASS")
        return 0

    print("DATA_COMPLIANCE_CHECK: FAIL")
    for issue in issues:
        print(f"- {issue}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())