#!/usr/bin/env python3
"""Build GB300e per-owner data (EOY 2025, US owners) from Epoch AI chip owners data.

Outputs site/data.js with per-owner medians + 90% CIs for three modes:
  - train_fp8: units x chip FP8 dense FLOP/s (fallback FP16; Google chips INT8) / GB300 FP8 (5 PF)
  - train_fp4: same but FP4 where available, else the FP8-chain value / GB300 FP4 (15 PF)
  - inference: units x chip mem BW / GB300 mem BW (8 TB/s)

CIs: Monte Carlo (N=20000), independent two-piece lognormal per (owner, chip) row
fitted to Epoch's 5th/50th/95th unit percentiles. Calibration check against
Epoch's own owner x designer aggregate CIs is printed.
"""
import csv, json, math, random

random.seed(42)
N_MC = 20000
DATA = "data/cumulative_by_chip_type.csv"
EOY = "2025-12-31"
US_OWNERS = ["Microsoft", "Google", "Meta", "Amazon", "Oracle", "CoreWeave", "xAI"]

# GB300 reference (Epoch ML Hardware DB, "NVIDIA GB300 (Blackwell Ultra)"):
GB300_FP8 = 5000e12   # dense FLOP/s
GB300_FP4 = 15000e12  # dense FLOP/s
GB300_BW = 8.0e12     # byte/s

# Per-chip specs, dense FLOP/s (e12 = TFLOPS) and mem BW (e12 byte/s).
# eff_fp8: FP8 if supported; else FP16/BF16; Google chips: INT8 (per KP's rule).
# eff_fp4: FP4 if supported; else eff_fp8 value.
# Sources: Epoch ML Hardware DB (ml_hardware.csv, pulled 2026-03-08) except where noted.
SPECS = {
    # chip bucket:        (eff_fp8, fp8_label, eff_fp4, fp4_label, bw, bw_note)
    "A100":            (312e12, "FP16, no FP8", 312e12, "FP16", 2.039e12, "A100 SXM 80GB"),
    "H100/H200":       (1979e12, "FP8", 1979e12, "FP8, no FP4", 4.075e12, "avg of H100 SXM 3.35 and H200 4.8"),
    "B200":            (5000e12, "FP8", 10000e12, "FP4", 8.0e12, "GB200 class"),
    "B300":            (5000e12, "FP8", 15000e12, "FP4", 8.0e12, "GB300"),
    "Trainium1":       (190e12, "FP16, no FP8", 190e12, "FP16", 0.82e12, ""),
    "Trainium2":       (1299e12, "FP8", 1299e12, "FP8, no FP4", 2.9e12, ""),
    "TPU v4":          (275e12, "INT8, Google rule", 275e12, "INT8", 1.2e12, ""),
    "TPU v4i":         (138e12, "BF16, no FP8", 138e12, "BF16", 0.614e12, ""),
    "TPU v5e":         (393e12, "INT8, Google rule", 393e12, "INT8", 0.819e12, ""),
    "TPU v5p":         (918e12, "INT8, Google rule", 918e12, "INT8", 2.765e12, ""),
    "TPU v6e":         (1836e12, "INT8, Google rule", 1836e12, "INT8", 1.64e12, ""),
    "TPU v7":          (4614e12, "FP8", 4614e12, "FP8, no FP4", 7.37e12, ""),
    "Instinct MI300X": (2614.9e12, "FP8, AMD datasheet", 2614.9e12, "FP8", 5.3e12, ""),
    "Instinct MI325X": (2614.9e12, "FP8, AMD datasheet", 2614.9e12, "FP8", 6.0e12, ""),
    "Instinct MI350X": (4600e12, "FP8", 9200e12, "FP4", 8.0e12, ""),
    "Instinct MI355X": (5033e12, "FP8, AMD datasheet", 10066e12, "FP4", 8.0e12, ""),
}

MODES = {
    "train_fp8": (0, GB300_FP8),
    "train_fp4": (2, GB300_FP4),
    "inference": (4, GB300_BW),
}


# Within-owner correlation of per-chip unit uncertainties (Gaussian copula, one
# common factor per owner). Tuned below so that our aggregated H100e CIs match
# Epoch's own published owner x designer CIs; independence (rho=0) gives CIs
# ~40% too narrow.
RHO = None  # set after tuning

def two_piece_from_z(med, s_lo, s_hi, z):
    s = s_hi if z > 0 else s_lo
    return med * math.exp(s * z)


def sample_owner_rows(rws, n, rho):
    """Draw correlated unit samples for one owner's chip rows. Returns {chip: [n draws]}."""
    sq_r, sq_i = math.sqrt(rho), math.sqrt(1 - rho)
    z90 = 1.6448536269514722
    params = {}
    for rw in rws:
        med, p5, p95 = rw["units_med"], rw["units_p5"], rw["units_p95"]
        params[rw["chip"]] = (med, (math.log(med) - math.log(p5)) / z90,
                              (math.log(p95) - math.log(med)) / z90)
    out = {c: [0.0] * n for c in params}
    for i in range(n):
        zc = random.gauss(0, 1)
        for c, (med, s_lo, s_hi) in params.items():
            z = sq_r * zc + sq_i * random.gauss(0, 1)
            out[c][i] = two_piece_from_z(med, s_lo, s_hi, z)
    return out


def pct(sorted_xs, q):
    i = q * (len(sorted_xs) - 1)
    lo, hi = int(math.floor(i)), int(math.ceil(i))
    frac = i - lo
    return sorted_xs[lo] * (1 - frac) + sorted_xs[hi] * frac


rows = [r for r in csv.DictReader(open(DATA)) if r["End date"] == EOY and r["Owner"] in US_OWNERS]
chips_seen = sorted(set(r["Chip type"] for r in rows))
missing = [c for c in chips_seen if c not in SPECS]
assert not missing, f"Missing specs for: {missing}"

owner_rows = {}
for r in rows:
    o = r["Owner"]
    p5s, p95s = r["Number of Units (5th percentile)"], r["Number of Units (95th percentile)"]
    has_ci = bool(p5s.strip()) and bool(p95s.strip())
    owner_rows.setdefault(o, []).append({
        "chip": r["Chip type"], "units_med": float(r["Number of Units (median)"]),
        "units_p5": float(p5s) if has_ci else None,
        "units_p95": float(p95s) if has_ci else None,
        "h100e_med": float(r["Compute estimate in H100e (median)"]),
    })

# ---- Tune RHO against Epoch's published owner x designer H100e CIs ----
des = [r for r in csv.DictReader(open("data/cumulative_by_designer.csv"))
       if r["End date"] == EOY and r["Owner"] in US_OWNERS]
DESIGNER_CHIPS = {
    "Nvidia": {"A100", "H100/H200", "B200", "B300"},
    "Google": {c for c in SPECS if c.startswith("TPU")},
    "Amazon": {"Trainium1", "Trainium2"},
    "AMD": {c for c in SPECS if c.startswith("Instinct")},
}

def designer_width_ratios(rho, n=4000):
    random.seed(7)
    ratios = []
    for r in des:
        o, dname = r["Owner"], r["Chip manufacturer"]
        if dname not in DESIGNER_CHIPS or not r["H100e (5th percentile)"].strip():
            continue
        sub = [rw for rw in owner_rows[o] if rw["chip"] in DESIGNER_CHIPS[dname] and rw["units_p5"]]
        if len(sub) < 2:
            continue
        draws = sample_owner_rows(sub, n, rho)
        sums = sorted(sum(draws[rw["chip"]][i] * rw["h100e_med"] / rw["units_med"] for rw in sub)
                      for i in range(n))
        ours_w = pct(sums, 0.95) - pct(sums, 0.05)
        theirs_w = float(r["H100e (95th percentile)"]) - float(r["H100e (5th percentile)"])
        ratios.append(ours_w / theirs_w)
    return ratios

best = None
for rho in [0.0, 0.3, 0.5, 0.7, 0.85, 1.0]:
    rr = designer_width_ratios(rho)
    err = sum(abs(math.log(x)) for x in rr) / len(rr)
    print(f"rho={rho:4.2f}  mean|log width ratio|={err:.3f}  ratios={[round(x,2) for x in rr]}")
    if best is None or err < best[1]:
        best = (rho, err)
RHO = best[0]
print(f"--> using RHO = {RHO}")

result = {"owners": [], "meta": {
    "eoy": EOY, "pulled": open("data/PULLED_UTC.txt").read().strip(),
    "gb300": {"fp8_pflops": GB300_FP8 / 1e15, "fp4_pflops": GB300_FP4 / 1e15, "bw_tbs": GB300_BW / 1e12},
    "n_mc": N_MC,
}}

result["meta"]["rho"] = RHO
random.seed(42)
for o in US_OWNERS:
    rws = owner_rows[o]
    has_ci = all(rw["units_p5"] is not None for rw in rws)
    draws = sample_owner_rows(rws, N_MC, RHO) if has_ci else None
    entry = {"owner": o, "has_ci": has_ci, "modes": {}, "chips": {}}
    for mode, (spec_i, denom) in MODES.items():
        ratios = {rw["chip"]: SPECS[rw["chip"]][spec_i] / denom for rw in rws}
        med_total = sum(rw["units_med"] * ratios[rw["chip"]] for rw in rws)
        m = {"median": med_total}
        if has_ci:
            sums = sorted(sum(draws[rw["chip"]][i] * ratios[rw["chip"]] for rw in rws)
                          for i in range(N_MC))
            m["p5"], m["p95"] = pct(sums, 0.05), pct(sums, 0.95)
        entry["modes"][mode] = m
        for rw in rws:
            entry["chips"].setdefault(rw["chip"], {"units": rw["units_med"]})[mode] = rw["units_med"] * ratios[rw["chip"]]
    result["owners"].append(entry)

# Spec table for the methodology section
result["meta"]["specs"] = {
    c: {"fp8_tflops": s[0] / 1e12, "fp8_label": s[1], "fp4_tflops": s[2] / 1e12,
        "fp4_label": s[3], "bw_tbs": s[4] / 1e12, "bw_note": s[5]}
    for c, s in SPECS.items() if c in chips_seen}

with open("docs/data.js", "w") as f:
    f.write("const DATA = " + json.dumps(result) + ";\n")

# ---- Report ----
print(f"{'Owner':<11} {'train_fp8 (k GB300e)':>24} {'train_fp4':>22} {'inference':>22}")
for e in result["owners"]:
    cells = []
    for mode in MODES:
        m = e["modes"][mode]
        if e["has_ci"]:
            cells.append(f"{m['median']/1e3:7.0f} [{m['p5']/1e3:.0f}-{m['p95']/1e3:.0f}]")
        else:
            cells.append(f"{m['median']/1e3:7.0f} [no CI]")
    print(f"{e['owner']:<11} {cells[0]:>24} {cells[1]:>22} {cells[2]:>22}")

