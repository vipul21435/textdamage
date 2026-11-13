"""Print a seeded random sample of proposed mojibake repairs with 30 characters of context on each side.

Usage: python scripts/sample_repairs.py FILE.jsonl[.gz] FIELD N_RECORDS K SEED

N_RECORDS > 0 first draws the same record sample as ``textdamage scan --sample N_RECORDS --seed SEED``
(0 means every record); then K accepted repairs are drawn with SEED and printed for reading one by one.
The output contains dataset text; it is meant for the terminal, not for committing.
"""
import random
import sys

from textdamage.io import iter_records
from textdamage.mojibake import find_mojibake
from textdamage.scan import reservoir

path, field, n_records, k, seed = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5])
recs = (r for r in iter_records(path, fmt="jsonl", fields=[field]) if not r.passthrough)
if n_records > 0:
    recs = reservoir(recs, n_records, seed)
hits = []
for r in recs:
    for _, v in r.fields:
        for h in find_mojibake(v):
            if h.fix is not None:
                hits.append((v[max(0, h.start - 30):h.start], h.text, h.fix, v[h.end:h.end + 30]))
print("accepted hits:", len(hits))
rng = random.Random(seed)
for i, (a, t, f, b) in enumerate(rng.sample(hits, min(k, len(hits)))):
    print(i, repr(a), "[", repr(t), "->", repr(f), "]", repr(b))
