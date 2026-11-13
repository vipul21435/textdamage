# textdamage

Scan the text fields of a dataset for mojibake, replacement characters, invisible and control characters,
mixed normalisation forms, look-alike letters from other scripts and broken escapes; count them per field and
source; and write a repaired copy only for the classes that can be repaired without guessing.

## Why this is hard

Damaged text is still valid Unicode, so nothing fails when it is loaded. The same characters can be correct in
one language and mojibake in another: `Ã` followed by `©` is almost always a broken `é`, but `ß` followed by a
German closing quote has the same shape and is correct. A repair that guesses wrong makes clean text worse. And
the damage usually sits in a few sources, so a dataset-wide rate hides where it comes from.

## Install

```
pip install git+https://github.com/vipul21435/textdamage
```

Python 3.10 or newer, no dependencies outside the standard library.

## Quickstart

`examples/sample.jsonl` holds five small records with deliberate damage.

```
$ textdamage scan examples/sample.jsonl --source-field source
# textdamage scan: sample.jsonl

Records: 5; with any damage: 4.

| class | records | share | occurrences | commonest sequences | example ids |
|---|---|---|---|---|---|
| mojibake | 2 | 40.00% | 3 | `Ã©` x1, `Ã¨` x1, `â<U+0080><U+0099>` x1 | r1, r2 |
| mojibake-2 | 1 | 20.00% | 2 | `ÃƒÂ©` x2 | r5 |
| invisible | 1 | 20.00% | 1 | `<U+200B>` x1 | r2 |
| bidi | 1 | 20.00% | 1 | `<U+202E>` x1 | r4 |
| entity | 1 | 20.00% | 1 | `&amp;` x1 | r4 |
...
```

The report goes on with a per-field table, a table of the proposed mojibake repairs (what `fix` would change)
and a per-source table; `--json` gives the same content as JSON.
One string, character by character (`-e` reads `\uXXXX` escapes in the argument):

```
$ textdamage explain -e 'it\u00e2\u0080\u0099s'
| # | char | code point | name | category | script | classes |
|---|---|---|---|---|---|---|
| 0 | i | U+0069 | LATIN SMALL LETTER I | Ll | LATIN |  |
| 1 | t | U+0074 | LATIN SMALL LETTER T | Ll | LATIN |  |
| 2 | â | U+00E2 | LATIN SMALL LETTER A WITH CIRCUMFLEX | Ll | LATIN | mojibake |
| 3 | <U+0080> | U+0080 |  | Cc |  | mojibake |
| 4 | <U+0099> | U+0099 |  | Cc |  | mojibake |
| 5 | s | U+0073 | LATIN SMALL LETTER S | Ll | LATIN |  |

- mojibake at 2..5: 'â<U+0080><U+0099>' -> '’'
```

A repaired copy, with a change log by id, never in place:

```
$ textdamage fix examples/sample.jsonl fixed.jsonl --repair mojibake,invisible
records: 5, changed: 3, unchanged and byte-identical: 2
  mojibake: 3 changes
  mojibake-2: 2 changes
  invisible: 1 changes
```

`fixed.jsonl.changes.jsonl` then holds one line per change, with ASCII escapes, such as
`{"id": "r1", "line": 1, "field": "text", "class": "mojibake", "before": "\u00c3\u00a9", "after": "\u00e9"}`.

Other commands and flags:

- `textdamage sources FILE --source-field F [--source-host]`: damage per source, worst first, and the share of
  all occurrences that the top k sources hold (`--top-sources k`, default 3). `--source-host` reduces a URL to
  its host name.
- `scan --max CLASS=N` or `--max CLASS=P%` (repeatable; CLASS may be `any`): exit 1 when a class has more than N
  occurrences or more than P % of records affected, for use in CI. Exit 2 is a usage or input error.
- `--ignore U+200D`, `--ignore U+FE00..U+FE0F`, `--ignore-file accepted.txt`: characters a project accepts; a
  finding made only of ignored characters is dropped, and `fix` never deletes them.
- `--field PATH` (repeatable, nested paths such as `messages[].content`), `--id-field`, `--classes`,
  `--repeat-min`, `--limit N`, `--sample N --seed S` (uniform reservoir sample of records).
- Input: JSON lines, JSON arrays, CSV, TSV and plain text (one record per line), each optionally gzip-compressed.
  Invalid JSON lines and CSV rows with the wrong column count are reported and skipped by `scan`, and passed
  through unchanged by `fix`. Bytes that are not valid UTF-8 are read as lone surrogates U+DC80..U+DCFF, counted
  as `surrogate` and written back unchanged.

The same functions are available from Python: `textdamage.detectors.scan_text`, `textdamage.scan.scan_file`,
`textdamage.fixer.fix_file` and `textdamage.mojibake.repair_mojibake`; `examples/scan_and_fix.py` uses them.

## How it works

Each class has one rule, written out in the docstring of `src/textdamage/detectors.py`. In short:

| class | rule |
|---|---|
| `mojibake`, `mojibake-2` | UTF-8 decoded once or twice as Latin-1 or Windows-1252, repair accepted (below) |
| `mojibake-ambiguous` | mojibake-shaped text whose repair failed the rule, in a value that also has accepted repairs; never changed |
| `replacement` | U+FFFD |
| `c0`, `c1` | C0 controls other than tab, LF and CR, and DEL; C1 controls U+0080..U+009F not inside an accepted mojibake hit |
| `invisible` | soft hyphen, zero width space, joiners, word joiner, invisible operators, fillers, variation selectors, tag characters; joiners and variation selectors after a symbol (emoji sequences), ZWNJ between letters of a script other than Latin, and tags after a black flag are not counted |
| `bidi` | the explicit directional formatting characters of UAX #9 (LRE, RLE, PDF, LRO, RLO, LRI, RLI, FSI, PDI, LRM, RLM) and U+061C |
| `bom` | U+FEFF inside a value (a byte-order mark at the start of a file is removed by the reader) |
| `non-nfc` | a combining sequence that NFC normalisation changes (UAX #15) |
| `compat` | compatibility characters of a formatting kind: decomposition tags `<font>`, `<narrow>`, `<circle>`, `<square>`, `<small>`, `<vertical>`, fullwidth letters, digits and symbols, Latin ligatures U+FB00..U+FB06; fullwidth punctuation is ordinary in CJK text and not counted |
| `confusable` | a word mixing Latin with Cyrillic or Greek letters whose minority-script letters are in a 50-pair confusable table |
| `escape` | literal `\n`, `\t`, `\r` (not before a lowercase letter, so LaTeX `\theta` is skipped), `\uXXXX`, `\UXXXXXXXX`, `\xXX`, outside Markdown code |
| `entity` | HTML character references (`&amp;`, `&#233;`, `&#xE9;`, any HTML5 named reference) outside Markdown code |
| `surrogate` | a lone surrogate code point |
| `repeat` | 10 or more (`--repeat-min`) identical punctuation characters, horizontal spaces inside a line, or blank lines, outside Markdown code; whole-line rules and Markdown table rows are skipped |

**Mojibake.** A mojibake sequence is a lead character U+00C2..U+00F4 followed by as many continuation
characters as its UTF-8 lead byte asks for, where a continuation character is anything Latin-1 or
Windows-1252 produces from a byte 0x80..0xBF (the five bytes Windows-1252 leaves undefined count as the matching
C1 controls). The sequence is mapped back to bytes and decoded as strict UTF-8; only sequences that decode are
candidates, and touching candidates form a group. A group is decoded once and, when the result still contains
candidates, a second time.

A repair is proposed only when the result scores as more plausible by a stated rule. The score, `badness`, is
the number of control, surrogate, private-use and unassigned characters, plus characters outside a fixed list
of commonly written script and symbol blocks (`COMMON_BLOCKS` in `src/textdamage/mojibake.py`), plus remaining
mojibake sequences. Every candidate group scores at least 1; the repair is accepted only when the repaired group
scores 0 and its first and last letters do not clash in script (Latin against Greek or Cyrillic) with the
letters next to it. Anything else is never changed. A rejected group counts as `mojibake-ambiguous` when the same
value holds an accepted repair (so does a lone `Â` or `Ã` before a space there, where the second byte was lost);
otherwise it is treated as ordinary text. Examples of each case are in `tests/test_mojibake.py`: the German
`ß` before a closing quote decodes to an NKo letter and is left alone; the Spanish `AQUÍ»` would end in a Greek
letter and is left alone.

This is close in spirit to the "badness" heuristic of ftfy (Speer), but simpler: ftfy weighs many character
categories, handles more encodings and fixes more kinds of damage. The tests compare the two on generated
mojibake in 20 languages and scripts, one and two rounds, and on clean text (`tests/test_ftfy_agreement.py`).

**Fix.** `fix` offers only `mojibake` (accepted hits), `bom`, `c0`, `c1`, `invisible` (deletes soft hyphen,
zero width space, word joiner, invisible operators, the Mongolian vowel separator and the deprecated format
characters, but keeps joiners, variation selectors, tags and fillers) and `non-nfc` (NFC is canonically
equivalent). The default is `mojibake` alone. A record with no change is written back as the exact bytes it was
read from; then the output is read back, each unchanged record is compared byte for byte with the input, and
`fix` exits 1 if any differ.

**Confusables.** The table in `src/textdamage/chars.py` has 50 Cyrillic and Greek letters that look like a single
Latin letter. `python scripts/check_confusables.py confusables.txt` checks every pair against the UTS #39 data
file; against version 18.0.0 (dated 2026-08-06) it reports `pairs in table: 50; not confirmed by the data file: 0`.

Sources:

- M. Davis and M. Suignard (eds.), *UTR #36: Unicode Security Considerations*, version 15, 2014-09-19,
  https://www.unicode.org/reports/tr36/ (stabilized; the page points to UTS #39 for current material).
- J. Hadley and R. Pournader (eds.), *UTS #39: Unicode Security Mechanisms*, version 18.0.0,
  https://www.unicode.org/reports/tr39/, and its data file `confusables.txt`.
- K. Whistler (ed.), *UAX #15: Unicode Normalization Forms*, Unicode 18.0.0, https://www.unicode.org/reports/tr15/.
- M. Goregaokar and R. Leroy (eds.), *UAX #9: Unicode Bidirectional Algorithm*, Unicode 18.0.0,
  https://www.unicode.org/reports/tr9/.
- R. Speer, *ftfy*, version 5.5, Zenodo, 2019, https://doi.org/10.5281/zenodo.2591652; documentation at
  https://ftfy.readthedocs.io/ ("Heuristics for detecting mojibake").
- N. Boucher, I. Shumailov, R. Anderson and N. Papernot, "Bad Characters: Imperceptible NLP Attacks", IEEE
  Symposium on Security and Privacy 2022, https://arxiv.org/abs/2106.09898.
- N. Boucher and R. Anderson, "Trojan Source: Invisible Vulnerabilities", USENIX Security Symposium 2023,
  https://arxiv.org/abs/2111.00169.

## Results on public data

Three public datasets from different sources, fetched with `scripts/fetch_data.sh data`. No rows are committed
here; the tables show counts and short damaged sequences only.

| dataset | file | licence (as stated on its page) |
|---|---|---|
| Databricks Dolly 15k (instructions written by people) | `databricks-dolly-15k.jsonl` | CC BY-SA 3.0 |
| OpenAssistant oasst1 (multilingual chat messages) | `2023-04-12_oasst_ready.messages.jsonl.gz` | Apache 2.0 |
| C4, English validation shard 0 of 8 (web text), 5,000 documents sampled with seed 1 | `c4-validation.00000-of-00008.json.gz` | ODC-BY, plus the Common Crawl terms of use |

Pages: https://huggingface.co/datasets/databricks/databricks-dolly-15k,
https://huggingface.co/datasets/OpenAssistant/oasst1, https://huggingface.co/datasets/allenai/c4.

Commands:

```
textdamage scan data/databricks-dolly-15k.jsonl --source-field category --json -o dolly.json
textdamage scan data/2023-04-12_oasst_ready.messages.jsonl.gz --field text --id-field message_id \
    --source-field lang --json -o oasst.json
textdamage scan data/c4-validation.00000-of-00008.json.gz --format jsonl --field text \
    --source-field url --source-host --sample 5000 --seed 1 --json -o c4.json
python scripts/table.py dolly=dolly.json oasst1=oasst.json c4-sample=c4.json
```

Dolly is scanned on every string field (instruction, context, response, category), oasst1 and C4 on the text.
Share of records with each class (number of records in brackets):

| class | dolly | oasst1 | c4-sample |
|---|---|---|---|
| records scanned | 15,011 | 88,838 | 5,000 |
| any damage | 0.23% (34) | 0.52% (460) | 2.50% (125) |
| mojibake | 0 | 0.00% (1) | 0.24% (12) |
| mojibake-ambiguous | 0 | 0 | 0.02% (1) |
| replacement | 0.03% (4) | 0 | 0.40% (20) |
| c0 | 0 | 0.00% (4) | 0.06% (3) |
| c1 | 0 | 0.00% (2) | 0.32% (16) |
| invisible | 0.12% (18) | 0.14% (126) | 0.42% (21) |
| bidi | 0.02% (3) | 0.00% (1) | 0.02% (1) |
| bom | 0.01% (1) | 0.01% (5) | 0.14% (7) |
| non-nfc | 0.01% (1) | 0.02% (16) | 0.16% (8) |
| compat | 0.01% (1) | 0.05% (45) | 0.04% (2) |
| confusable | 0.03% (4) | 0.03% (27) | 0.10% (5) |
| escape | 0 | 0.08% (72) | 0.02% (1) |
| entity | 0.01% (1) | 0.03% (26) | 0.54% (27) |
| repeat | 0.01% (1) | 0.17% (147) | 0.18% (9) |

Commonest sequences (occurrences):

- dolly: replacement U+FFFD 28; invisible U+200B 17, U+2060 8, U+200D 4; compat ligatures `ﬁ` 6 and `ﬂ` 6.
- oasst1: invisible U+200B 268, U+00AD 85, U+034F 29; compat mathematical sans-serif bold letters (the three
  commonest 41, 35 and 32); escape literal `\n` 196, `\r` 17, `\t` 7; entity `&nbsp;` 41; bom U+FEFF 41;
  c1 U+0095 10; one mojibake hit, `â€™`.
- c4-sample: mojibake 111 hits in 12 documents, commonest `â€™` 19, `Ã¼` 19, `â€“` 14, `Ã¶` 11, `â€œ` 10;
  replacement U+FFFD 194; c1 U+0097 51 and U+0092 27 (the Windows-1252 positions of the em dash and the right
  single quote); entity `&apos;` 83 and `&amp;` 11; invisible U+200B 37.

Where it comes from (the `sources` part of each report):

- dolly by category: the top 3 of 8 categories (summarization, closed_qa, information_extraction) hold 72.5 % of
  all occurrences and 29.8 % of records.
- oasst1 by language: the top 3 of 25 languages (en, es, ru) hold 91.2 % of occurrences and 82.1 % of records.
- c4-sample by host: 4,929 hosts; the top 3 hosts, one document each (0.06 % of records), hold 24.8 % of all
  occurrences.

**Proposed repairs, read one by one.** `python scripts/sample_repairs.py data/c4-validation.00000-of-00008.json.gz
text 5000 40 1` prints 40 of the 111 accepted mojibake repairs in the C4 sample (seed 1) with 30 characters of
context; the oasst1 file has a single accepted repair (same script with `text 0 40 1`), and Dolly none.
Of the 41 read one by one: 40 right, 1 wrong, 0 unclear. The wrong one is a sequence that had been damaged twice
with two of its characters lost on the way (`Ã¢â¬â¢` where a full double encoding of `’` is `Ã¢â‚¬â„¢`): the
rule repaired the first pair to `â` and left `â¬â¢`, so the text is changed but not restored.

Run time, measured on a loaded laptop: 26 s for Dolly (13 MB), 135 s for oasst1 (34 MB compressed), 29 s for
the C4 sample (reading and sampling the 40 MB compressed shard included).

## Limitations

- Mojibake is detected only for UTF-8 read as Latin-1 or Windows-1252. Other code pages (Windows-1251,
  Shift-JIS, GBK, MacRoman), UTF-16 and damage with lost bytes are not repaired; the last can be partly
  repaired, as in the wrong case above.
- The script of a letter is taken from the first word of its Unicode name, because the standard library has no
  Script property. That is right for the scripts the rules use, but it is an approximation.
- Counts include legitimate uses: literal `\n` in prose about code outside backticks, entities in text about
  HTML, soft hyphens placed on purpose, bold mathematical letters used as styling. Use `--ignore`, `--classes`
  and the per-field tables to separate them.
- The confusable table covers only Latin, Cyrillic and Greek, one letter to one letter, 50 pairs. Whole-script
  confusables (a word written entirely in Cyrillic look-alikes) are not detected.
- `fix` rewrites a changed JSON line with `json.dumps(..., ensure_ascii=False)` and a changed CSV row with the csv
  module, so the formatting of changed records can differ from the input. It does not support JSON arrays.
  Parquet and other binary formats are not read.
- The repair sample read one by one is small (41 repairs) and comes from two of the three datasets.
- Pure Python, one core; the run times above give the speed.

## Related tools

- [ftfy](https://github.com/rspeer/python-ftfy) fixes mojibake and many other kinds of damage with a richer
  heuristic; textdamage counts per field and source and repairs a narrower set.
- [sftlint](https://github.com/vipul21435/sftlint) lints chat and tool-calling datasets.
- [snippetcheck](https://github.com/vipul21435/snippetcheck) checks the code inside datasets.
- [datasieve](https://github.com/vipul21435/datasieve) removes duplicates from training data.
- [datadelta](https://github.com/vipul21435/datadelta) compares two versions of a dataset.

## Licence

MIT, see `LICENSE`.

Built by Vipul Raj Jha · https://vipul21435.github.io
