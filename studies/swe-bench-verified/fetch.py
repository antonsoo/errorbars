# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""Rebuild data/outcomes.json from the public SWE-bench experiments repository.

    uv run studies/swe-bench-verified/fetch.py

Every SWE-bench Verified submission publishes which of the 500 tasks it
resolved (github.com/SWE-bench/experiments, evaluation/verified/). This reads
those lists at one pinned commit and packs them into a single small file: one
record per submission, with its outcomes as a 500-bit hex string.

Only the facts needed for the statistics are kept (who resolved what, and the
leaderboard's own metadata tags). Trajectories, logs and logos are not fetched.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import urllib.request
from pathlib import Path
from typing import Any

import yaml

REPO = "SWE-bench/experiments"
# Pinned so the numbers in README.md can be reproduced exactly. Pass --commit to refresh.
COMMIT = "40f164d5b8f1d249bf95a6df8b74b577fd8e519d"
SPLIT = "evaluation/verified"
N_INSTANCES = 500
WANTED = ("metadata.yaml", "metadata.yml", "results/results.json", "per_instance_details.json")
PEEK_REPORT = "git_peek_suspicious_commits.md"

HERE = Path(__file__).parent


def _get(url: str, token: str | None = None) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "errorbars-study"})
    if token:
        request.add_header("Authorization", f"Bearer {token}")
    last: Exception | None = None
    for _ in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except OSError as exc:  # URLError and timeouts
            last = exc
    raise RuntimeError(f"could not fetch {url}: {last}")


def download(commit: str, cache: Path) -> list[str]:
    """Fetch the per-submission files into ``cache`` and return their relative paths."""
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    tree_url = f"https://api.github.com/repos/{REPO}/git/trees/{commit}:{SPLIT}?recursive=1"
    tree = json.loads(_get(tree_url, token))
    if tree.get("truncated"):
        raise RuntimeError("GitHub truncated the file listing; the layout has outgrown this script")
    paths = [
        entry["path"]
        for entry in tree["tree"]
        if entry["type"] == "blob" and (entry["path"].endswith(WANTED) or entry["path"].endswith(PEEK_REPORT))
    ]

    def one(path: str) -> None:
        target = cache / commit / path
        if target.exists() and target.stat().st_size:
            return
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(_get(f"https://raw.githubusercontent.com/{REPO}/{commit}/{SPLIT}/{path}"))

    with concurrent.futures.ThreadPoolExecutor(12) as pool:
        list(pool.map(one, paths))
    return paths


def _bits_to_hex(bits: list[int]) -> str:
    return f"{int(''.join(map(str, bits)), 2):0{len(bits) // 4}x}"


def _checked(value: Any) -> bool | None:
    # The tag is a bool, null, or a sentence starting with "false".
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower().startswith("true")
    return None


def build(commit: str, cache: Path) -> dict[str, Any]:
    root = cache / commit
    resolved: dict[str, set[str]] = {}
    evaluated: dict[str, set[str]] = {}
    meta: dict[str, dict[str, Any]] = {}
    peeked: dict[str, int] = {}
    without_outcomes: list[str] = []
    for directory in sorted(p for p in root.iterdir() if p.is_dir()):
        name = directory.name
        for candidate in ("metadata.yaml", "metadata.yml"):
            if (directory / candidate).exists():
                meta[name] = yaml.safe_load((directory / candidate).read_text()) or {}
        details = directory / "per_instance_details.json"
        results = directory / "results" / "results.json"
        if details.exists():
            per_instance = json.loads(details.read_text())
            resolved[name] = {iid for iid, row in per_instance.items() if row.get("resolved")}
            evaluated[name] = set(per_instance)
        elif results.exists():
            resolved[name] = set(json.loads(results.read_text())["resolved"])
        else:
            without_outcomes.append(name)
        report = directory / PEEK_REPORT
        if report.exists():
            for line in report.read_text().splitlines():
                if line.startswith("Total highlighted trajectories:"):
                    peeked[name] = int(line.split(":")[1])

    instances = sorted(max(evaluated.values(), key=len))
    if len(instances) != N_INSTANCES:
        raise RuntimeError(f"expected {N_INSTANCES} task ids, found {len(instances)}")
    known = set(instances)
    submissions = []
    for name, solved in resolved.items():
        if solved - known:
            raise RuntimeError(f"{name} lists tasks outside SWE-bench Verified: {sorted(solved - known)[:3]}")
        tags = meta.get(name, {}).get("tags") or {}
        info = meta.get(name, {}).get("info") or {}
        covered = evaluated.get(name, known)
        record: dict[str, Any] = {
            "id": name,
            "name": info.get("name") or name,
            "date": f"{name[:4]}-{name[4:6]}-{name[6:8]}",
            "resolved": _bits_to_hex([int(i in solved) for i in instances]),
            "n_resolved": len(solved),
            # The percentage the submission's own metadata states, where it states one.
            "reported": info.get("resolved"),
            "agent": tags.get("agent"),
            "models": tags.get("model") or [],
            "org": tags.get("org"),
            "checked": _checked(tags.get("checked")),
            "attempts": str((tags.get("system") or {}).get("attempts") or "") or None,
            "open_source_system": tags.get("os_system"),
            "open_weights_model": tags.get("os_model"),
        }
        if len(covered) < N_INSTANCES:
            # A run that stopped early: say which tasks it reported at all.
            record["evaluated"] = _bits_to_hex([int(i in covered) for i in instances])
            record["n_evaluated"] = len(covered)
        if name in peeked:
            record["git_history_flags"] = peeked[name]
        submissions.append(record)
    return {
        "source": {
            "repository": f"https://github.com/{REPO}",
            "commit": commit,
            "path": SPLIT,
            "note": (
                "Derived from the per-task outcome lists that each submission publishes. "
                "Bit i of 'resolved' (most significant first) is instances[i]."
            ),
        },
        "instances": instances,
        "submissions": submissions,
        "without_outcomes": without_outcomes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--commit", default=COMMIT, help="commit of SWE-bench/experiments to read")
    parser.add_argument("--cache", type=Path, default=HERE / "cache", help="where to keep downloads")
    parser.add_argument("--output", type=Path, default=HERE / "data" / "outcomes.json")
    args = parser.parse_args()
    paths = download(args.commit, args.cache)
    data = build(args.commit, args.cache)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, separators=(",", ":"), ensure_ascii=False) + "\n")
    print(
        f"{len(paths)} files at {args.commit[:7]}: {len(data['submissions'])} submissions with outcomes, "
        f"{len(data['without_outcomes'])} without; wrote {args.output} ({args.output.stat().st_size:,} bytes)"
    )


if __name__ == "__main__":
    main()
