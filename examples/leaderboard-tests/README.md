# Which test forms a leaderboard group?

`two-questions.csv` is a deliberately tiny **synthetic counterexample**, not
an evaluation benchmark. Candidate scores 1 on both questions; baseline scores
0 on both. The paired differences have zero variance, so the paired-t
convention reports p=0. But there are only two discordant binary questions:
the exact two-sided binomial probability is 2 / 2^2 = 0.5.

`before.json` is the real CLI output at revision `26bcc3f`: separate groups.
`after.json` is the repaired CLI output: one group, `mcnemar_exact`, p=0.5.
The paired-t value is retained as a diagnostic and no longer selects the group.

`repeated.csv` is another synthetic boundary case: every question has two
generations. Its observed question means happen to be 0 or 1, but averaging
several draws does not turn them into single binary trials. It retains the
paired-t path and its explicit zero-variance warnings; this change is not a
new distribution-free test for repeated-generation means.

```bash
uv run errorbars leaderboard examples/leaderboard-tests/two-questions.csv
uv run python scripts/verify_leaderboard_tests.py --out /tmp/leaderboard-workflows.json
```

The second command checks the tiny case, repeated generations, the existing
clustered reading-comprehension example, and the **actual lm-eval COPA captures**
in `tests/fixtures/lm_eval_output`. It computes the native COPA discordant
counts independently using only Python's standard library. Add
`--executable /path/to/installed/errorbars` to replay a wheel installation.
`workflows.json` retains the reports and input hashes.

[Decision rules and public-data audit](../../docs/leaderboard-tests.md).
