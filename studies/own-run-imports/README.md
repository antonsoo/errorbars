# Malformed reports are not zero-resolution runs

The SWE-bench study's CSV exporter previously used a truthiness fallback when
selecting `resolved_ids` or the legacy `resolved` field. Values such as `null`,
`false`, zero, an empty object and an empty string became an empty set. Every one
of the 500 tasks was then exported with score zero. A nonempty object whose keys
were task IDs also became a resolved set, despite not being a list.

Both aliases could produce inconsistent results: an empty `resolved_ids` list
could be replaced by a nonempty `resolved` list. The browser used different
fallback rules and could silently choose one alias or ignore an invalid secondary
field. These are constructed malformed inputs, not claimed production incidents.

Both entry points now require present result fields to be lists of strings. If
both aliases appear, their task sets must agree. Order and repeated IDs do not
matter. Explicit empty lists remain valid. Invalid reports fail before any
CSV is emitted; invalid browser pastes leave the previous comparison intact.

## Before and after

Baseline: `fac30b143f7c99f6b75e8b80b64a41f3af317a96`.
`replay.py` exercises the actual exporter as a subprocess. `browser.mjs` drives
exactly the same report objects through the built app in Chromium and Firefox
at 375 and 1440 pixels, offline after local fonts and figures have loaded.

| Workflow | Before | After |
| --- | ---: | ---: |
| Malformed CLI inputs rejected without CSV or traceback | 4/22 | 22/22 |
| Malformed CLI inputs accepted as results | 16/22 | 0/22 |
| Valid JSON CLI controls accepted | 6/6 | 6/6 |
| Malformed browser pastes rejected, prior comparison preserved | 72/88 | 88/88 |
| Valid browser pastes accepted | 24/24 | 24/24 |

A downstream check turns the malformed `{"resolved_ids": null}` report into an
apparent 4.4-point loss against the real `20231010_rag_claude2` run, with exact
McNemar p = 0.0000004768. That is analysis of invented zero scores, not evidence
about a personal model. The corrected exporter emits no CSV for this input;
`results/downstream.json` retains the actual CLI result and corrected error.

The two other baseline CLI failures leaked type errors. Every corrected failure
exits 1 with an input diagnostic. Valid zero-result, modern/legacy and equivalent
alias reports retain identical CSV bytes. A repeated-ID plain-text control also
matches the valid JSON export exactly.

All **175 retained submissions** produce the same **87,500 CSV rows**, byte for
byte, before/after. This includes the study's documented contradictory submissions
and partial coverage policy; unchanged export is not endorsement of every input.
A separately fetched, pinned public `20231010_rag_claude2` result report also
exports identical 500 rows with 22 resolved tasks. Its URL, input hash and output
hash are in `results/public-report.json`. No public report was edited to make it
malformed. The four after screenshots were visually inspected.

## Reproduce

```sh
uv run python studies/own-run-imports/replay.py --work /tmp/errorbars-own-run --out /tmp/own-run-after.json
cd web && npm ci && npm run build && cd ..
node studies/own-run-imports/browser.mjs web/dist /tmp/errorbars-own-run/cases.json /tmp/own-run-browser
```

For a baseline, pass `--exporter` pointing to `to_csv.py` from the baseline commit,
plus `--observe-only`. The data file is held constant. Build that commit's web app
and pass its `dist` to the browser script with `--observe-only`. Scripts keep their
HTTP server local and close it after replay. Browser receipts hash every served
asset; error paths in CLI results are normalized to `<work>`.

To repeat the public-report control, download the pinned URL recorded in
`results/public-report.json`, verify its recorded SHA-256, and run each exporter
with `--mine public-run=downloaded-results.json` against the same `--data` file.

## Scoring policy and limits

A separate coverage hypothesis was checked and discarded: the study explicitly
scores unreported tasks as unresolved for leaderboard reproduction. This change
preserves that policy and the 500-task denominator. It does not infer that every
task was observed, validate completion, or turn the study into an observed-only
comparison. Users still need to interpret its documented benchmark policy.

The modern harness writes a string list in `resolved_ids`; older public result
files use `resolved`. See [SWE-bench's report writer](https://github.com/SWE-bench/SWE-bench/blob/main/swebench/harness/reporting.py)
and the pinned legacy report in the receipt. Other harness metadata is outside
these checks. JSON duplicate-key handling and the existing plain-text syntax are
unchanged. The browser additionally supports a bare JSON array, as before.

The changes affect a repository study script and the web app. No Python package
runtime file, package version or statistical formula changes.
