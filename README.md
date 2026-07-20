# US AI chip owners in GB300-equivalents (EOY 2025)

Interactive figure: cumulative AI-chip installed base of the seven US owners Epoch AI names
(Microsoft, Google, Meta, Amazon, Oracle, CoreWeave, xAI) at end of 2025, converted to
GB300-equivalents, with 90% CIs and a three-mode toggle:

1. **Training & Inference Prefill FP8** — dense FP8 FLOP/s ÷ GB300 FP8 (5 PFLOP/s); no-FP8 chips use FP16/BF16, Google TPUs without FP8 use INT8.
2. **Training & Inference Prefill FP4** — dense FP4 ÷ GB300 FP4 (15 PFLOP/s), falling back to the FP8-chain value.
3. **Inference Decode** — memory bandwidth ÷ GB300's 8 TB/s.

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

Built by a team of Konstantin's Claudes, 2026-07-20.
