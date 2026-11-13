# Changelog

## 0.1.0

- Detectors with documented rules for mojibake (one and two rounds, and ambiguous cases), replacement
  characters, C0 and C1 controls, invisible characters, directional controls, byte-order marks inside text,
  non-NFC sequences, compatibility characters, mixed-script words with a confusable letter, literal escapes,
  HTML entities, lone surrogates and repeated runs.
- Mojibake repair that is proposed only when the repaired text scores 0 on a stated plausibility rule.
- `scan` with reports per class, field and source in Markdown or JSON; `--max` limits for CI; an ignore list.
- `explain` for one string, character by character.
- `fix` for the safe classes only, with a change log by id and a byte-identical round-trip check of unchanged
  records; never edits in place.
- `sources` table with the share of damage held by the top sources.
- Readers for JSON lines, JSON arrays, CSV, TSV and plain text, optionally gzip-compressed.
- Results on Dolly 15k, OpenAssistant oasst1 and a C4 sample in the README.
