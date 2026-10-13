# A useful leaderboard must survive exponentially many overlapping groups

At baseline `f4dd23f`, a constructed 1,177,625-byte CSV with 50 models and
1,024 binary questions failed with `MemoryError` under a 512 MiB Linux address
space limit. It printed no report. The pairwise tests were inexpensive; the
failure came from materializing 33,554,432 overlapping non-significance groups.
Even the terminal command did this work, although it displays exact pairwise
rank comparisons rather than the group lists.

The source now limits this optional summary. All model estimates, paired tests,
Holm corrections, exact rank comparisons and SVG export remain available when
group enumeration cannot finish. No partial group list is published.

## The reproducible score table

[cases.py](cases.py) constructs 25 pairs of binary score columns. Each base
column is a balanced parity function of the 1,024 question numbers. Its partner
corrects exactly 16 zeroes: the means are 0.5 and 0.515625. Distinct base columns
are orthogonal. These are authored inputs, not measured models, representative
evaluation traffic or a statistical power study.

There are 1,225 model pairs. Within each original/corrected pair, exact
McNemar's two-sided p-value is `2 / 2**16 = 1 / 32768`; Holm-adjusted p is
`1225 / 32768 = 0.037384033203125`. Every cross-pair adjusted p-value is 1.
Consequently, a maximal non-significance group chooses exactly one member of
each original/corrected pair: `2**25 = 33,554,432` groups. This count follows
from the verified graph; the study does not need to enumerate all of them.

The existing pivoted Bron-Kerbosch search helps dense tied boards but cannot
avoid an exponentially large output. The
[NetworkX clique documentation](https://networkx.org/documentation/stable/reference/algorithms/generated/networkx.algorithms.clique.find_cliques.html)
describes this output-size limitation. Switching algorithms or using an iterator
alone would not make storing and exporting all those groups practical.

Generate the exact table and run the repaired source:

```sh
uv run python studies/group-enumeration/cases.py /tmp/group-scores.csv
uv run errorbars leaderboard /tmp/group-scores.csv --json > /tmp/group-board.json
uv run errorbars leaderboard /tmp/group-scores.csv --plot /tmp/group-board.svg
```

## Complete, omitted and untested are different states

The source adds `group_status` to every leaderboard JSON result. `groups`
contains the complete list when available, or `null` when its enumeration was
omitted. Python callers must likewise handle `Leaderboard.groups is None`.

| group_status | groups | Meaning |
| --- | --- | --- |
| `complete` | list | All maximal groups were enumerated. |
| `omitted_group_limit` | `null` | More than 4,096 groups were found. |
| `omitted_search_limit` | `null` | Search reached 50,000 visited states with unfinished work. |

An omitted summary includes `group_limits` with both configured bounds and a
warning in JSON and the terminal. A result with exactly 4,096 groups can still
complete. The search budget limits traversal as well as output count; neither
is a whole-program memory or latency guarantee. Input size and pairwise
analysis still have their own costs. There is no automatic approximate grouping.

`untested_pairs` continues to describe pairs with insufficient shared questions
or clusters. Group-summary omission does not add untested pairs or change any
significance decision. For example, the constructed 50-model case retains one
significantly different partner and 48 non-significant partners for every model.
Non-significance does not establish equivalence.

The full non-significance graph remains reconstructible from `pairwise`, even
when its redundant maximal-group listing is unavailable.

## Verification method

[replay.py](replay.py) runs actual CLI processes under the same 512 MiB address
space and 8 MiB output-file limits, with a 30-second watchdog. It checks every
raw McNemar p-value using integer binomial tails and every Holm-adjusted value
using rational arithmetic. It verifies every rank comparison, all model means,
small complete groups, the large explicit omission and successful SVG export.
It needs Linux resource limits and `/usr/bin/time`:

```sh
uv run python studies/group-enumeration/replay.py \
  --python .venv/bin/python --source . --out /tmp/group-replay
```

Omit `--source` and supply a separately installed environment's Python to check
a wheel. `--small-only` also works against the baseline. The controls contain
16 models / 256 groups and 24 models / exactly 4,096 groups. Their complete
reports remain unchanged apart from the added `group_status` field.

The unit oracle exhaustively enumerates subsets independently of Bron-Kerbosch
for all 1,024 five-node graphs. It checks both budget boundaries and the
50-model inference outcome. [public_replay.py](public_replay.py) also replays
the retained 173 usable SWE-bench Verified submissions under question-level
and repository-clustered inference. It compares every prior report field,
including groups and warnings, not just headline scores. The source data is
the existing pinned [outcomes file](../swe-bench-verified/data/outcomes.json);
this is not a new crawl or a fresh evaluation-accuracy study.

No package release or hosted deployment is part of this source repair.

## Retained outcomes

[The baseline failure](results/failure-before.json) records exit 1, no report
and a `MemoryError` from clique enumeration under the address-space limit.
The [clean CLI replay](results/clean-cli.json) finishes all four commands under
the same limit. Its 50-model JSON and terminal/SVG runs peak at 75,352 and
75,232 KiB RSS respectively. The failed baseline peaked at 406,300 KiB RSS;
address-space limits also count mapped memory, so this is not a 512 MiB RSS
measurement. These are individual resource observations on this machine,
not production timing or universal memory guarantees.

The complete 50-model exports are retained as
[compressed JSON](results/large-report.json.gz),
[terminal output](results/large-terminal.txt) and [standalone SVG](results/large.svg).
The SVG was rendered and inspected; all 50 visible model labels and the summary
omission warning remain present. [Export hashes](results/exports.json) identify
the exact files. No output contains an arbitrary first subset of groups.

[Before](results/public-before.json) and [clean-build](results/public-clean.json)
public replays retain every prior report field unchanged for 173 usable
submissions and 500 questions. Both inference scopes contain 14,878 pairwise
tests. The question-level report retains all 117 groups; the repository-clustered
report retains both groups. Only the new `group_status: "complete"` field is
excluded from their whole-report hash comparison. Two submissions remain
excluded by the existing reported-score consistency rule.

[verification.json](results/verification.json) records a clean archive of
implementation `1e2ab7a`: locked install, lint, types, 680 tests, sdist and wheel.
All 471 tracked entries match the archive commit. The CLI inspection harness
has its own recorded hash; production code did not change after this archive.
The 181,716-byte wheel rebuilt from the sdist has SHA-256
`65c8f4a1932352955471b651093bb1cd9353a9cde1c988b85e9b3f5a3496df0f`.
It is byte-identical to the first wheel.

Fresh installs on [Python 3.10.21 / NumPy 1.24.0](results/cli-minimum.json) and
[Python 3.14.7 / NumPy 2.5.4](results/cli-current.json) each match all 27 package
source/asset files. All three complete JSON exports and the SVG match the clean
build, with every pair independently checked and all four commands completing
under the same limits. The package version remains 0.2.4; this does not publish
the repair to PyPI or update a hosted application.
