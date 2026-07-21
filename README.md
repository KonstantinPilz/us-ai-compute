# US AI chip owners in GB300-equivalents (EOY 2025)

Interactive figure: cumulative AI-chip installed base of the seven US owners Epoch AI names
(Microsoft, Google, Meta, Amazon, Oracle, CoreWeave, xAI) at end of 2025, converted to
GB300-equivalents, with 90% CIs and a three-mode toggle:

1. **FP8 FLOP/s** — dense FP8 FLOP/s ÷ GB300 FP8 (5 PFLOP/s); no-FP8 chips use FP16/BF16, Google TPUs without FP8 use INT8.
2. **FP4 FLOP/s** — dense FP4 ÷ GB300 FP4 (15 PFLOP/s), falling back to the FP8-chain value.
3. **Memory Bandwidth** — memory bandwidth ÷ GB300's 8 TB/s.

**Live site:** https://konstantinpilz.github.io/us-ai-compute/

## Files

1. `build_data.py` — pipeline: reads `data/cumulative_by_chip_type.csv`, computes the three modes,
   tunes within-owner correlation ρ against Epoch's published owner×designer CIs (ρ = 0.7),
   runs a 20k-draw Monte Carlo, writes `docs/data.js`.
2. `data/` — Epoch AI "Data on AI Chip Owners" (CC-BY 4.0), pulled date in `data/PULLED_UTC.txt`.
3. `docs/` — the static site (GitHub Pages serves this directory).

## Updating

```bash
curl -sL https://epoch.ai/data/ai_chip_owners.zip -o /tmp/aco.zip && unzip -o /tmp/aco.zip -d data/
date -u +%Y-%m-%d > data/PULLED_UTC.txt
python3 build_data.py   # regenerates docs/data.js; check the rho fit + calibration output
```

Chip specs are hardcoded in `build_data.py` (`SPECS`), sourced from Epoch's ML Hardware DB
(`~/research/ml-hardware/ml_hardware.csv`) plus AMD datasheet overrides for MI300X/MI325X/MI355X FP8/FP4.
If Epoch adds new chip types, the script fails with an assert listing the missing specs.

## Locked companion section (#labs)

The index page ends with a password-protected "Chinese AI developers" section. Its data ships as
`docs/labs_data.js` — AES-256-GCM ciphertext only (PBKDF2-SHA256, 300k iterations), decrypted
client-side after the password is entered; `docs/labs.html` just redirects to `/#labs`. A local
hourly script (`sync_labs.py`, deliberately not in this repo) syncs the blob from an internal
model, validating the source structure strictly and failing loudly — without publishing — if the
source layout changes (new rows, renamed headers, moved tables). The section has the same
FP8/FP4/Memory-Bandwidth dropdown as the main figure: FP8 shows the source values verbatim;
FP4 and Memory Bandwidth rescale medians and CIs by per-entity factors computed from each
entity's chip mix (read and validated from the source each sync).

Built by a team of Konstantin's Claudes, 2026-07-20.
