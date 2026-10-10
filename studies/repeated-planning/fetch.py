"""Retain only binary grading outcomes from two pinned public repeated-sampling runs.

Downloads about 701 MB once to the ignored cache. Never executes generated code,
contacts a model, or retains question/answer text in the derived artifact.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REVISION = "a9f8f73bcd6948a57ed922cba4e48062ef95f553"
BASE = f"https://huggingface.co/datasets/ScalingIntelligence/monkey_business/resolve/{REVISION}"
FILES = {
    "GSM8K_Llama-3-8B-Instruct.json": "0e334c7010a2eb39ab0aaf38cdd196da0b6219a95fd69f82d35b8f51e46ed765",
    "GSM8K_Llama-3-70B-Instruct.json": "22ff8a363d5a5b8ea5a6c299285d8f615ec32b9c1fe08e8253cc1a6c9c7c323f",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    cache = ROOT / "cache"
    cache.mkdir(exist_ok=True)
    sources, datasets = [], []
    for name, expected in FILES.items():
        path = cache / name
        if not path.exists():
            partial = path.with_suffix(".part")
            with urllib.request.urlopen(f"{BASE}/{name}", timeout=60) as response, partial.open("wb") as out:
                for chunk in iter(lambda: response.read(1024 * 1024), b""):
                    out.write(chunk)
            if sha256(partial) != expected:
                raise ValueError(f"checksum mismatch: {name}")
            partial.replace(path)
        if sha256(path) != expected:
            raise ValueError(f"checksum mismatch: {name}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        assert len(raw) == 127
        questions = []
        for index, row in enumerate(raw):
            outcomes = row["is_corrects"]
            assert len(outcomes) == len(row["samples"]) == 10_000
            assert all(type(value) is bool for value in outcomes)
            assert row["orig_dset_split"] == "test"
            content = json.dumps([row["question"], row["gt_answer"]], ensure_ascii=False).encode("utf-8")
            questions.append(
                {
                    "question_id": str(row["orig_dset_idx"]),
                    "source_record_index": index,
                    "question_target_sha256": hashlib.sha256(content).hexdigest(),
                    "correct": "".join("1" if value else "0" for value in outcomes),
                }
            )
        assert len({q["question_id"] for q in questions}) == 127
        datasets.append({"source": name, "questions": questions})
        sources.append(
            {"file": name, "url": f"{BASE}/{name}", "sha256": expected, "bytes": path.stat().st_size}
        )
        print(f"{name}: retained {len(questions)} questions x 10,000 outcomes")
    payload = {"schema_version": 1, "datasets": datasets}
    derived = gzip.compress((json.dumps(payload, indent=2) + "\n").encode("utf-8"), mtime=0)
    (ROOT / "outcomes.json.gz").write_bytes(derived)
    manifest = {
        "dataset": "ScalingIntelligence/monkey_business",
        "revision": REVISION,
        "sources": sources,
        "outcomes_sha256": hashlib.sha256(derived).hexdigest(),
        "outcomes_bytes": len(derived),
        "encoding": "Each correct string preserves source sample order: 1=True, 0=False from is_corrects.",
        "license": "MIT per the pinned dataset card; only grading labels, IDs and hashes are redistributed.",
    }
    (ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
