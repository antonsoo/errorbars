# SWE-bench personal-run import verification

The study exporter and browser now reject non-list result fields and conflicting
`resolved_ids` / `resolved` aliases. An explicit empty list still represents zero
resolved tasks under the study's documented 500-task leaderboard policy.

Implementation: `cbd38582d1289c9f60d4e589c35c08a0a57c8c83`.
Baseline: `fac30b143f7c99f6b75e8b80b64a41f3af317a96`.
[Study and replay](../studies/own-run-imports/README.md).

The CLI baseline accepted 16 of 22 malformed report objects. A null result list
became 500 zero scores; compared with a real 22-resolution public run, it yielded
an apparent -4.4-point gap with exact McNemar p = 0.0000004768. The corrected
exporter exits 1 with no CSV. All 22 malformed controls fail without a traceback;
all six valid JSON controls and the plain-text control retain their exact output.

All 175 retained submissions export the same 87,500 rows byte for byte, including
the study's explicitly documented policy for unreported tasks. The pinned public
legacy report `20231010_rag_claude2` also retains all 500 exported rows, with 22
resolved tasks. No claim is made that malformed constructed reports occurred in
production or that the unchanged submissions are all valid scientific evidence.

## Actual browsers

The identical 28 report objects were pasted into Chromium and Firefox at 375 and
1440 pixels. Networking was disabled after loading local fonts and figures.

| Actual paste workflow | Baseline | Corrected |
| --- | ---: | ---: |
| Invalid report rejected with previous comparison preserved | 72/88 | 88/88 |
| Valid report accepted | 24/24 | 24/24 |

All four corrected screenshots were visually inspected. The replay recorded no
page errors, requests after going offline or page-width overflow. The comparison
table's complete text was checked before and after every rejected paste; errors
cannot silently replace the prior result. `results/browser-*.json` records each
case, status text, table hash and served-asset hashes.

## Clean checkout and runtime checks

A fresh archive of the implementation commit passes:

| Check | Result |
| --- | --- |
| Python 3.12.12, frozen dependencies | Ruff, strict mypy over 18 package files, 655 tests |
| Node 24.21.0, fresh npm install | ESLint, TypeScript/Vite build, 691 tests |
| Chromium/Firefox production-build workflows | 52 passed, including 88 invalid pastes in the four new workflows |
| Python 3.10.21 and 3.14.7 | Full study exporter replay identical to the Python 3.12 result |
| Source/archive/build/served bytes | 428 archived files, 65 build files, 61 served assets agree |

The Python 3.10/3.14 checks run the repository study script; this script is not
part of the wheel. No Python runtime package file, package metadata, lockfile or
statistical formula changed. A new package build would not exercise this fix.
The web study remains a static application; no hosted deployment was performed.

The [build receipt](../studies/own-run-imports/results/build.json) lists every
compared output's SHA-256. Validation logs, runtime replays and the public-report
receipt are retained beside it. New verification documents and receipts were
added after the implementation archive; executable inputs were unchanged.

These checks validate the selected result-list schema and alias agreement, not
all harness metadata or benchmark completion. JSON duplicate-key behavior and
plain-text parsing remain unchanged. The documented leaderboard denominator is
preserved, rather than replaced with an observed-only estimate.
