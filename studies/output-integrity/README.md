# Exporting a report must not erase its input

At source baseline `8d13a98`, actual CLI commands could exit successfully after
destroying the evidence they had just analyzed:

| Command/destination | Before | Corrected source |
| --- | --- | --- |
| `leaderboard scores.csv --plot scores.csv` | Replaces the 32,836-byte score table with a 5,435-byte SVG | Error; input bytes unchanged |
| `import lm-eval samples_...jsonl --model example -o samples_...jsonl` | Replaces the 19,266-byte native log with a 2,470-byte CSV | Error; native log unchanged |
| `compare scores.csv --html report.html`, where the input is a link to `report.html` | Replaces the underlying score table with HTML | Error; source and link unchanged |
| CSV/SVG write fails after 1,024 bytes | Earlier completed export is replaced by a partial file | Earlier export unchanged; no temporary file remains |

These are local fault and path-layout reproductions using copies of the
repository's existing inputs, not reports of production incidents. The repair
is source only; no PyPI release or hosted deployment is claimed.

## What is protected

All CLI file exports use one writer. It rejects a destination that resolves to
a loaded input or has the same filesystem identity, including input aliases
through symlinks, hard links and linked directories. The loader also records
the matching `results_<timestamp>.json` used to identify an lm-eval model:
erasing that file would remove provenance even if the sample log survived.

A symbolic-link destination is refused, including a dangling link. Normal
directories reached through a parent symlink remain usable. Directories and
other nonregular destinations are refused; a FIFO no longer hangs while the
CLI waits for a reader. The temporary name has a fixed short prefix, so a
valid 255-byte report filename does not become an overlong temporary filename.

CSV rows stream to a private sibling temporary file; SVG and HTML use the same
writer. Only a complete write, flush, filesystem sync and close is followed by
replacement of the destination. Failure leaves the previous output intact and
removes the temporary file. New and replaced outputs have mode 0600 on POSIX.
This is not a lock against concurrent writers or a guarantee that a directory
entry survives a whole-machine power loss. No multi-output transaction is claimed.

`write_csv(data, path)` protects the source paths already recorded in `data`;
callers may supply additional `protected` paths. A `ComparisonReview` holds
display basenames for privacy, so direct Python callers pass original input
paths to `write_comparison_html(review, path, protected=paths)`. The CLI does
this automatically. Relative paths are interpreted in the caller's current
working directory. An output path cannot be recognized as an unrelated source
that was never supplied or read; the chosen ordinary destination is still
replaced on a successful export.

## Executable replay

[`replay.py`](replay.py) copies the existing synthetic reading-comprehension
table and retained lm-eval COPA log into disposable directories. The receipt
pins both originals by size and SHA-256. It creates the specified filesystem
layouts, invokes `python -m errorbars.cli` as a separate process, and records
exit status, errors and every file's before/after bytes and SHA-256. Symlinks
are recorded without following them; the FIFO is never opened by the observer.
The constructed model-identity sidecar is explicitly test data.

Partial-write cases use the operating system's `RLIMIT_FSIZE`, with a 1,024-byte
limit and `SIGXFSZ` ignored so the actual write reports an I/O error. This is not
a mocked writer. Both the CSV and SVG baseline leave exactly 1,024 bytes in
place of the prior 25-byte export. HTML already wrote atomically and is retained
as a control. The corrected code preserves that earlier 25-byte file for all
three formats and leaves no extra filesystem entries.

Across 36 cases, the [baseline](results/before.json) meets **14/36** intended
outcomes and the [corrected source](results/after.json) meets **36/36**. There
are 24 refusal/failure cases and 12 successful-export controls. The baseline
already handles three refusal/failure controls correctly (empty input, directory
destination and interrupted HTML write); they are not counted as newly fixed.
Its FIFO case times out after ten seconds. Its full-length HTML filename fails;
the other 11 successful controls produce **byte-identical exports** after the
repair. The new full-length HTML export also succeeds.

The input/output bytes and export serialization are the main evidence. Focused
regressions additionally verify source-alias rejection in all three CLI routes,
sidecar protection, direct CSV API protection, complete
replacement, temporary cleanup and preservation when synchronization fails.
No calculation, report template, browser script or style changed.

## Clean build and installed wheel

A fresh archive of implementation `4633de1` completed `uv sync --locked --group
dev --extra all --python 3.12`, ruff, mypy, all **676 Python checks**, and
`uv build`. The build used Python 3.12.12. All 459 tracked files remained
byte-identical. See the [verification receipt](verification.json) and
[full-suite log](results/clean-tests.txt).

The resulting wheel was installed separately in two new environments, with
only the package and NumPy. All 27 package source and asset files matched the
clean archive in both installations:

| Installed environment | NumPy | Replay | Export hashes and filesystem outcomes |
| --- | --- | --- | --- |
| Python 3.10.21, declared minimum Python series | 1.24.0, dependency floor | [36/36 correct](results/installed-minimum.json) | Match corrected source |
| Python 3.14.7 | 2.5.4 | [36/36 correct](results/installed-current.json) | Match corrected source |

Both installed entry points also completed `--version` and the documented
`power --delta 0.03 --baseline 0.5` command. Native Inspect and other optional
dependencies were included in the full clean-source checks, not these minimal
wheel environments. No optional package was needed for the output replay.

| Local artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `errorbars-0.2.4-py3-none-any.whl` | 180869 | `fc5c7bfc97433d8aa895ff50607f71d71048536a4db6b4b95018341810fbd258` |
| `errorbars-0.2.4.tar.gz` | 246004 | `4d56cd3ba65a81579d7459dfa5caeb1b63995bd9e94d5b4f2c88a8aa18cd92f3` |

The wheel was built from the source distribution. These are local artifact
checks; version remains 0.2.4 and neither artifact was uploaded to PyPI.

## Reproduce

From a source checkout with dependencies installed:

```sh
python3 studies/output-integrity/replay.py --python .venv/bin/python \
  --source src --label checkout --work /tmp/errorbars-output-check > /tmp/errorbars-output-check.json
```

The script needs POSIX support for links, FIFOs and the file-size limit. It
always prints observed results, including baseline disagreements; inspect
`disagreements` and require zero for a corrected build. For installed-wheel
verification, point `--python` at the installed environment and omit `--source`.
For the baseline, archive `8d13a98` separately and pass that archive's `src`.
All destructive specimens are disposable copies; the repository inputs are
never selected as output destinations.
