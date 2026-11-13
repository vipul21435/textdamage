# textdamage

Scan the text fields of a dataset for mojibake, replacement characters, invisible and control characters,
mixed normalisation forms, look-alike letters from other scripts and broken escapes, and count them per field
and source.

Status: early. The detectors, the mojibake repair rule, the `scan` and `explain` commands and the readers for
JSON lines, JSON, CSV/TSV and plain text work and are tested. `fix`, CI thresholds and the `sources` command
are not written yet.

## Install

```
pip install git+https://github.com/vipul21435/textdamage
```

## Quickstart

```
textdamage scan examples/sample.jsonl --source-field source
textdamage explain -e 'cafÃ©'
```

## Licence

MIT.

Built by Vipul Raj Jha · https://vipul21435.github.io
