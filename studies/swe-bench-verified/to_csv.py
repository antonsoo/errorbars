"""Write per-task scores for chosen submissions in the CSV format the errorbars CLI reads.

    uv run python studies/swe-bench-verified/to_csv.py ID [ID ...] [--mine NAME=FILE] > scores.csv
    uv run python studies/swe-bench-verified/to_csv.py --list

ID is a submission directory name from SWE-bench/experiments, or a unique part
of one. --mine adds a run of your own: FILE is the evaluation report the
SWE-bench harness writes (a JSON object with "resolved_ids" or "resolved"), or a
text file with one resolved task id per line. Those resolved-only own-run inputs
retain the documented full-benchmark convention: absent tasks count as unresolved.
Public submissions with an explicit evaluated mask export only recorded outcomes;
an observed-subset mean is not the official resolved / 500 benchmark score.

The repository of each task goes in the cluster_id column, so errorbars also
reports the repository-level comparison. Pass --cluster-col none to the CLI to
leave it out.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from cohorts import TaskOutcomes, decode_submission

HERE = Path(__file__).parent


def _own_run(spec: str, known: set[str]) -> tuple[str, set[str]]:
    name, _, file = spec.partition("=")
    if not file:
        raise SystemExit("--mine takes NAME=FILE")
    text = Path(file).read_text(encoding="utf-8-sig")
    try:
        report = json.loads(text)
    except json.JSONDecodeError:
        resolved = {line.strip() for line in text.splitlines() if line.strip()}
    else:
        if not isinstance(report, dict) or not ({"resolved_ids", "resolved"} & report.keys()):
            raise SystemExit(f'{file}: expected a JSON object with "resolved_ids" or "resolved"') from None
        lists = {key: report[key] for key in ("resolved_ids", "resolved") if key in report}
        for key, value in lists.items():
            if not isinstance(value, list) or any(not isinstance(iid, str) for iid in value):
                raise SystemExit(f'{file}: "{key}" must be a list of task id strings')
        # Empty lists are real zero-resolution results. Falsey malformed values
        # must not become empty lists, or fall through to a different alias.
        resolved = set(next(iter(lists.values())))
        if any(set(value) != resolved for value in lists.values()):
            raise SystemExit(f'{file}: "resolved_ids" and "resolved" disagree')
    unknown = sorted(resolved - known)
    if unknown:
        raise SystemExit(
            f"{file}: {len(unknown)} ids are not SWE-bench Verified tasks (first: {unknown[0]!r})"
        )
    return name, resolved


def main() -> None:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("ids", nargs="*", metavar="ID")
    parser.add_argument("--mine", action="append", default=[], metavar="NAME=FILE")
    parser.add_argument("--list", action="store_true", help="print the submission ids and scores")
    parser.add_argument("--data", type=Path, default=HERE / "data" / "outcomes.json")
    args = parser.parse_args()

    data = json.loads(args.data.read_text())
    instances: list[str] = data["instances"]
    by_id = {sub["id"]: sub for sub in data["submissions"]}
    if args.list:
        decoded = [decode_submission(sub, instances) for sub in data["submissions"]]
        for sub in sorted(decoded, key=lambda s: -len(s.resolved)):
            suffix = f"  [{len(sub.evaluated)}/{sub.total} outcomes recorded]" if not sub.complete else ""
            print(f"{100 * len(sub.resolved) / sub.total:5.1f}  {sub.name}{suffix}")
        return

    columns: list[TaskOutcomes] = []
    for wanted in args.ids:
        matches = [wanted] if wanted in by_id else [sid for sid in by_id if wanted in sid]
        if len(matches) != 1:
            hint = ", ".join(matches[:4]) if matches else "see --list"
            raise SystemExit(f"{wanted!r} names {len(matches)} submissions ({hint})")
        columns.append(decode_submission(by_id[matches[0]], instances))
    for spec in args.mine:
        name, resolved = _own_run(spec, set(instances))
        columns.append(TaskOutcomes(name, frozenset(resolved), frozenset(instances), len(instances)))
    if not columns:
        parser.error("name at least one submission, or --mine NAME=FILE")

    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(["question_id", "model", "score", "cluster_id"])
    for sub in columns:
        if not sub.complete:
            print(
                f"notice: {sub.name}: exporting {len(sub.evaluated)} recorded task outcomes "
                f"from a {sub.total}-task benchmark; "
                f"{sub.total - len(sub.evaluated)} unobserved tasks omitted. "
                "Means describe the observed subset, not the official full-benchmark score.",
                file=sys.stderr,
            )
        for iid in instances:
            if iid in sub.evaluated:
                writer.writerow([
                    iid, sub.name, int(iid in sub.resolved), iid.rsplit("-", 1)[0].replace("__", "/")
                ])


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        raise SystemExit(f"error: {exc}") from None
