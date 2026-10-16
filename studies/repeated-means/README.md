# Identical grades cannot gain significance by being repeated

The baseline source (`8dbb12c`) gives models with identical raw `0.1` grades a
paired difference of `-1.3877787807814457e-17`, p=0 and separate leaderboard
groups when one run has one observation per question and the other has three.
The first rounded sum is divided by the repetition count and rounded again.
Repeating the same distribution can produce the same problem even when the
grades within a question vary.

The corrected source accumulates exact ratios of the stored binary64 grades and
rounds once after division, using `statistics.mean`. Single observations retain
their direct path. Original grades, question weights, inference selection and
zero-variance warnings remain available. No rounding threshold discards small
input differences. This is local source work; no package release or hosted
deployment is included.

## Actual workflows

Two controlled native Inspect runs were recorded with **inspect-ai 0.3.268**
and its built-in mockllm provider: twenty identical questions, one or three epochs,
and an explicit scorer returning numeric `0.1` for every observation. All 80 raw
grades agree, and the adapter verifies twenty matching question signatures and
matching scorer declarations. Native logs were retained without rewriting.
They contain synthetic answers and grades; no model API or external grader was
called. [Capture code](capture.py), [manifest](fixtures/manifest.json),
[one epoch](fixtures/epochs-1.eval), [three epochs](fixtures/epochs-3.eval).

Two CSV controls use the standard library's CSV writer: `constant` records one
`0.1` grade per pattern; `same_distribution` records `[0.1, 0.2, 0.3]`. Three
labelled runs repeat each question's pattern once, three times or ten times.
Each CSV has twenty questions; repetitions are observations, not extra questions.
[Constant CSV](fixtures/constant.csv), [repeated-distribution CSV](fixtures/same_distribution.csv).

| Input | Baseline selected p, once vs triple | Corrected selected p | Baseline / corrected board groups |
|---|---:|---:|---|
| CSV, constant grade | 0 | 1 | 2 / 1 |
| CSV, repeated three-grade distribution | 0 | 1 | 2 / 1 |
| Native Inspect, one vs three epochs | 0 | 1 | 2 / 1 |

[Before](results/before.json) and [after](results/after.json) retain actual CLI
results, original observation counts, inference names, warnings and implementation
hashes. The CLI also writes complete JSON and standalone HTML to its work directory.
The corrected comparisons have zero question-level differences. A group records
non-significance; it does not establish population equivalence. The existing
constant-difference t-test convention still reports its degeneracy warning.

The regression checks use independent integer-rational input means, reordered
and replicated mixed grades, negative and small scores, legal large scores and
NumPy integer grades. A genuine one-ULP input difference survives unchanged in
the paired difference. That is a numerical control, not a claim of meaningful
population evidence from such a small difference. Arithmetic operates on the
stored binary64 grades, not the original decimal spelling.

## Reproduce

With the source checkout installed, replay the CSV cases:

```bash
python studies/repeated-means/replay.py --work /tmp/repeated-means --out /tmp/repeated-means.json
```

Add `--native` when the Inspect extra is installed. `NAME=PATH` gives the two
native runs distinct comparison labels. To record fresh native logs:

```bash
uv run --locked python studies/repeated-means/capture.py /tmp/repeated-means-native
```

Inspect capture times, IDs and log hashes will differ. To replay the baseline,
archive `8dbb12c` and set `PYTHONPATH` to its `src/` while running the current
driver. The driver copies inputs under its work directory, so exported evidence
uses portable relative source paths.

## Cost of accurate averaging

[`measure.py`](measure.py) runs the actual CLI three times on a **210,000-row
synthetic CSV**: 5,000 questions and three copies of the same grade distribution
at different repetition counts. Input bytes and SHA-256 agree before and after.

| Full CSV/leaderboard workload | Baseline median | Corrected median |
|---|---:|---:|
| Wall time | 3.71 s | 3.61 s |
| Child CPU time | 4.13 s | 4.11 s |

[Raw baseline timings](results/timing-before.json) and
[corrected timings](results/timing-after.json) retain all three samples and their
actual groups/p-values. These are measurements on a shared 14-vCPU WSL2 Linux
host with 48 GB RAM, Python 3.12.12; the overlapping ranges do not establish a
speedup. Exact-ratio averaging does more work for repeated grades. The measured
workload remains usable, and single-observation means avoid that work. Repeat:

```bash
python studies/repeated-means/measure.py --work /tmp/repeated-means-timing --out /tmp/repeated-means-timing.json
```
