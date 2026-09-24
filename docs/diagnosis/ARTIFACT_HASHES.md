# R4 artifact digests

Written from `sha256sum` output. Artifacts over 5 MB are gitignored and
regenerate deterministically from `run_funnel.py` with the settings recorded in
each arm's `run_metadata.json`.

| file | bytes | sha256 |
|---|--:|---|
| `out/disambig_legacy/trace.jsonl` | 14172163 | `d528d370b8b0478f22b1f419d09152a3d27cff1ed827136bae3ed86ff50fc212` |
| `out/disambig_legacy/results.json` | 8077596 | `cdd9e73f9a9c2b480645724b35ceb185beed0a05cbc5ee1f999c6bef887270b0` |
| `out/disambig_scored/trace.jsonl` | 14198790 | `7f633231f7ad2010b37f254c31ffcca510bd1278809b40ca730ccd46fb731303` |
| `out/disambig_scored/results.json` | 8078516 | `7a216e2a8c3c2200188e560b5967a80f5097f541afd1f62e9acdb835758e63b3` |
