# Refuse table imports that discard or invent values

Two constructed inputs exposed lossy imports at `211611f`:

- A pandas DataFrame can contain two columns called `score`. Its `to_dict` warns,
  discards one column, and returns ordinary records. Errorbars previously continued
  with those records. In the 40-question reproduction, the first column gives
  A - B = +0.2 and the last gives -0.2. Neither interpretation is justified without
  choosing a column. Errorbars now refuses duplicate column labels before conversion.
- Python's default CSV reader repairs an unfinished quoted field at EOF. A final
  score of `"0` was accepted as zero; a malformed `"0"0` also became zero.
  These inputs could overwrite an existing comparison report or normalized export.
  Errorbars now uses strict CSV parsing and translates parser errors into located
  `ValueError`s, handled by the CLI before any output is written.

This is an import correctness check, not evidence of a production incident or an
assessment of the quality of any model.

## Recorded results

`replay.py` drives the library and real `python -m errorbars.cli` processes. The
before run imports the archived baseline; the after run imports the corrected tree.
The same generated files and commands are used for both.

| Check | Before | After |
| --- | ---: | ---: |
| Duplicate DataFrame column cases rejected before conversion | 0/8 | 8/8 |
| Malformed CSV cases rejected with path and physical line | 0/12 | 12/12 |
| CLI failures with located error, no traceback/stdout, and preserved output files | 0/48 | 48/48 |
| Valid constructed CSV variants retaining every value | 48/48 | 48/48 |
| Valid DataFrames, including duplicate indexes and custom columns | 3/3 | 3/3 |

Six malformed CSV cases were accepted by the old library. The other six already
failed, but lacked the intended parser diagnostic or leaked `csv.Error` through the
CLI. Eighteen baseline commands overwrote an output file. Each after command exits
1 and preserves the existing HTML, SVG and CSV guard files.

The valid cases exercise comma, semicolon and tab delimiters, minimal/all quoting,
LF/CRLF, UTF-8 BOM, decimal commas, embedded quotes and newlines, and presence/absence
of a final newline. Full normalized records, including physical source lines, match
before/after. All seven retained example/study CSV files (1,557 records) also match.
Two retained public SWE-bench submissions, exported through the existing `to_csv.py`
script, contribute another 1,000 unchanged records. Their pinned upstream source,
submission IDs and input hash are in the result files; this checks import stability,
not upstream completeness or the converter's treatment of other submissions.

The valid CLI comparison's JSON and standalone HTML are byte-identical before/after.
`browser.mjs` opens that actual report offline in Chromium and Firefox at 375 and
1440 pixels, inspects multiline source records, filters eight A-higher questions,
and downloads the complete 40-question JSON and filtered CSV. The separate web demo
does not import CSV and is outside this change.

## Reproduce

From the repository root, after `uv sync --group dev --extra all`:

```sh
uv run python studies/table-imports/replay.py --work /tmp/errorbars-table-imports --out /tmp/after.json
cd web && npm ci && cd ..
node studies/table-imports/browser.mjs /tmp/errorbars-table-imports/comparison.html /tmp/errorbars-table-browser
```

For a baseline, archive `211611faf3bb66ec24688a43b66a27ea3e1a9a8d` into a separate
checkout, set `PYTHONPATH` to its `src` directory, and run the same script with
`--observe-only`. For an installed wheel, run the script with that environment's
Python and no source `PYTHONPATH`. Reuse `--work` sequentially, never concurrently.
Recorded error paths replace this directory with `<work>`; CLI errors retain their
last line plus an explicit traceback flag. Valid-record hashes normalize source
paths to file names so results are independent of the temporary directory.

## Boundaries and references

- Duplicate DataFrame **row indexes** remain supported. Observation identity comes
  from configured question/model/sample columns. Duplicate columns, even unused
  ones, require explicit selection or renaming, as duplicate CSV headers already do.
- This uses Python's documented CSV dialect, not a new RFC conformance validator.
  Bare quotes in unquoted fields retain the standard reader's behavior. A closed
  final quoted field without a newline is valid.
- Detecting unfinished quotes does not prove dataset completeness. Removed whole
  records or a truncated unquoted value can still be syntactically valid.
- The physical line in a parser error is where parsing failed, including lines
  consumed within an unfinished multiline record; it is not a question identifier.

References: [Python CSV dialect strictness](https://docs.python.org/3.14/library/csv.html#csv.Dialect.strict)
and [pandas duplicate labels](https://pandas.pydata.org/docs/user_guide/duplicates.html).
The implementation adds no runtime dependency; pandas remains optional.
