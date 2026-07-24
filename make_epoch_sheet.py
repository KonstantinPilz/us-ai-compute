#!/usr/bin/env python3
"""Build the 'US AI Chip Owners — GB300e Conversions' Google Sheet from the same
inputs as build_data.py: Epoch unit counts (values, sourced) + chip specs
(values, sourced) + conversions and totals as live formulas. MC confidence
intervals are pasted from docs/data.js and marked as model outputs.

Regenerate after re-running build_data.py: ./make_epoch_sheet.py [--sid SID]
(with --sid it clears and rewrites the existing sheet in place).
"""
import csv, json, re, sys, urllib.request, urllib.parse

ROOT = "/home/ubuntu/research/us-owners-gb300e"
CREDS = "/home/ubuntu/.google_workspace_mcp/credentials/konstantinsclaude@gmail.com.json"
EOY = "2025-12-31"
US_OWNERS = ["Microsoft", "Google", "Meta", "Amazon", "Oracle", "CoreWeave", "xAI"]
EPOCH_URL = "https://epoch.ai/data/ai-chip-owners"
HWDB_URL = "https://epoch.ai/data/machine-learning-hardware"
FIGURE_URL = "https://konstantinpilz.github.io/us-ai-compute/"

# chip -> (fp8 TFLOP/s, fp8 basis, fp4 TFLOP/s, fp4 basis, bw TB/s, bw note, source label, source url)
SPECS = {
    "A100":            (312, "FP16 (no FP8 hardware)", 312, "falls back to FP16", 2.039, "A100 SXM 80 GB", "Epoch ML Hardware DB", HWDB_URL),
    "H100/H200":       (1979, "FP8", 1979, "falls back to FP8 (no FP4)", 4.075, "average of H100 SXM (3.35) and H200 (4.8)", "Epoch ML Hardware DB", HWDB_URL),
    "B200":            (5000, "FP8 (GB200 class)", 10000, "FP4", 8.0, "GB200 class", "Epoch ML Hardware DB", HWDB_URL),
    "B300":            (5000, "FP8 (GB300 class)", 15000, "FP4", 8.0, "GB300", "Epoch ML Hardware DB", HWDB_URL),
    "Trainium1":       (190, "FP16 (no FP8 hardware)", 190, "falls back to FP16", 0.82, "", "Epoch ML Hardware DB", HWDB_URL),
    "Trainium2":       (1299, "FP8", 1299, "falls back to FP8 (no FP4)", 2.9, "", "Epoch ML Hardware DB", HWDB_URL),
    "TPU v4":          (275, "INT8 (Google-chip rule)", 275, "falls back to INT8", 1.2, "", "Epoch ML Hardware DB", HWDB_URL),
    "TPU v4i":         (138, "BF16 (no FP8 hardware)", 138, "falls back to BF16", 0.614, "", "Epoch ML Hardware DB", HWDB_URL),
    "TPU v5e":         (393, "INT8 (Google-chip rule)", 393, "falls back to INT8", 0.819, "", "Epoch ML Hardware DB", HWDB_URL),
    "TPU v5p":         (918, "INT8 (Google-chip rule)", 918, "falls back to INT8", 2.765, "", "Epoch ML Hardware DB", HWDB_URL),
    "TPU v6e":         (1836, "INT8 (Google-chip rule)", 1836, "falls back to INT8", 1.64, "", "Epoch ML Hardware DB", HWDB_URL),
    "TPU v7":          (4614, "FP8", 4614, "falls back to FP8 (no FP4)", 7.37, "", "Epoch ML Hardware DB", HWDB_URL),
    "Instinct MI300X": (2614.9, "FP8", 2614.9, "falls back to FP8 (no FP4)", 5.3, "", "AMD MI300X datasheet", "https://www.amd.com/en/products/accelerators/instinct/mi300/mi300x.html"),
    "Instinct MI325X": (2614.9, "FP8", 2614.9, "falls back to FP8 (no FP4)", 6.0, "", "AMD MI325X datasheet", "https://www.amd.com/en/products/accelerators/instinct/mi300/mi325x.html"),
    "Instinct MI350X": (4600, "FP8", 9200, "FP4", 8.0, "", "Epoch ML Hardware DB", HWDB_URL),
    "Instinct MI355X": (5033, "FP8", 10066, "FP4", 8.0, "", "AMD MI355X specifications", "https://www.amd.com/en/products/accelerators/instinct/mi350/mi355x.html"),
}


def token():
    c = json.load(open(CREDS))
    data = urllib.parse.urlencode({"client_id": c["client_id"], "client_secret": c["client_secret"],
        "refresh_token": c["refresh_token"], "grant_type": "refresh_token"}).encode()
    return json.load(urllib.request.urlopen(
        urllib.request.Request("https://oauth2.googleapis.com/token", data=data), timeout=60))["access_token"]


def api(tok, method, url, body=None):
    req = urllib.request.Request(url, method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))


# ---- load inputs ----
rows = [r for r in csv.DictReader(open(f"{ROOT}/data/cumulative_by_chip_type.csv"))
        if r["End date"] == EOY and r["Owner"] in US_OWNERS]
pulled = open(f"{ROOT}/data/PULLED_UTC.txt").read().strip()
data_js = open(f"{ROOT}/docs/data.js").read()
DATA = json.loads(re.match(r"const DATA = (.*);\n", data_js, re.S).group(1))
mc = {o["owner"]: o for o in DATA["owners"]}
rho = DATA["meta"]["rho"]

owner_rows = {}
for r in rows:
    owner_rows.setdefault(r["Owner"], []).append(r)
for o in owner_rows:
    owner_rows[o].sort(key=lambda r: -float(r["Compute estimate in H100e (median)"]))

chips = sorted({r["Chip type"] for r in rows})
chip_row = {c: 7 + i for i, c in enumerate(chips)}   # spec-tab data rows (1-indexed)

# ================= Tab 2: chip specs =================
S = "'2. Chip specs & ratios'"
specs_vals = [
    ["Table 2: Chip specifications and GB300e conversion ratios"],
    ["Each chip is converted at spec ÷ GB300 reference (row 4). FP8 mode uses dense FP8 FLOP/s, falling back to FP16/BF16 (Google chips: INT8). FP4 mode uses dense FP4 where the chip has it, otherwise the FP8-basis value (so a non-FP4 chip is worth 1/3 of its FP8-mode value). Memory-bandwidth mode uses HBM bandwidth. Judgment call: Epoch's B200 and B300 owner buckets are valued at GB200-class (5,000 FP8 / 10,000 FP4 / 8 TB/s) and GB300-class (5,000 / 15,000 / 8) specs rather than Epoch's standalone B200/B300 rows (4,500 / 9,000 / 7.7) — matching the H100-equivalent ratios Epoch itself applies to those buckets, which imply rack-scale GB-class GPUs. Using the standalone specs instead would lower the US FP8 total by about 4%."],
    [],
    ["GB300 reference (denominators)", "FP8 dense TFLOP/s", 5000, "FP4 dense TFLOP/s", 15000, "Memory bandwidth TB/s", 8],
    [],
    ["Chip", "Effective dense throughput (TFLOP/s or TOPS; basis in next column)", "FP8 basis", "Dense FP4 TFLOP/s", "FP4 basis", "Memory BW (TB/s)", "BW note",
     "GB300e per chip — FP8 mode", "GB300e per chip — FP4 mode", "GB300e per chip — BW mode", "Spec source"],
]
for i, c in enumerate(chips):
    s = SPECS[c]
    rr = 7 + i
    specs_vals.append([
        c, s[0], s[1], s[2], s[3], s[4], s[5],
        f"=B{rr}/$C$4", f"=D{rr}/$E$4", f"=F{rr}/$G$4",
        f'=HYPERLINK("{s[7]}", "{s[6]}")',
    ])

# ================= Tab 3: counts & conversion =================
C = "'3. Epoch counts & conversion'"
conv_vals = [
    ["Table 3: Epoch unit counts and GB300e by owner and chip"],
    [f"Unit counts (columns C–E) are Epoch AI's cumulative installed-base estimates for December 31, 2025, pulled {pulled}. GB300e columns are formulas: units × the ratio from tab 2. Owner subtotal rows add the chip rows above them and feed Table 1 on the Overview tab."],
    [],
    ["Owner", "Chip", "Units p5 (Epoch)", "Units median (Epoch)", "Units p95 (Epoch)",
     "GB300e median — FP8 mode", "GB300e median — FP4 mode", "GB300e median — BW mode", "Source"],
]
subtotal_row = {}
rr = 5
for o in US_OWNERS:
    first = rr
    for r in owner_rows[o]:
        c = r["Chip type"]
        sr = chip_row[c]
        p5 = float(r["Number of Units (5th percentile)"]) if r["Number of Units (5th percentile)"].strip() else ""
        p95 = float(r["Number of Units (95th percentile)"]) if r["Number of Units (95th percentile)"].strip() else ""
        conv_vals.append([
            o if rr == first else "", c, p5, float(r["Number of Units (median)"]), p95,
            f"=D{rr}*{S}!H{sr}", f"=D{rr}*{S}!I{sr}", f"=D{rr}*{S}!J{sr}",
            f'=HYPERLINK("{EPOCH_URL}", "Epoch AI chip owners")' if rr == first else "",
        ])
        rr += 1
    conv_vals.append([f"{o} total", "", "", "", "",
                      f"=SUM(F{first}:F{rr - 1})", f"=SUM(G{first}:G{rr - 1})", f"=SUM(H{first}:H{rr - 1})", ""])
    subtotal_row[o] = rr
    rr += 1

# ================= Tab 1: Overview =================
ov_vals = [
    ["US AI Chip Owners — GB300e Conversions"],
    [f"This sheet converts Epoch AI's US chip-owner unit counts (EOY 2025) into GB300-equivalents for the owners figure at {FIGURE_URL}. "
     "Written by a team of Konstantin's Claudes."],
    ["How this estimate works. Epoch AI publishes cumulative installed-base unit counts per owner and chip type (tab 3, values with source links). "
     "Each chip type gets a GB300e conversion ratio from its specifications (tab 2): the chip's spec divided by the GB300 reference — 5,000 dense FP8 TFLOP/s, 15,000 dense FP4 TFLOP/s, or 8 TB/s of memory bandwidth, depending on the toggle mode. "
     "Owner totals below are formulas that add units × ratio over the owner's chips; nothing in the median columns is hand-entered."],
    ["Method note (confidence intervals). The p10/p90 columns are 80% intervals — reported at 80% for comparability with our Chinese-company estimates, though Epoch publishes 5th/50th/95th percentiles. They are Monte Carlo outputs, not formulas: 20,000 draws per owner from two-piece lognormals fitted to Epoch's per-chip unit percentiles, "
     f"with a shared within-owner correlation factor (Gaussian copula, rho = {rho}) tuned so the aggregated intervals match Epoch's own published owner-by-designer H100e intervals. Independence would give intervals about 40% too narrow. "
     f"Intervals computed {pulled[:10]}; re-running build_data.py then make_epoch_sheet.py in ~/research/us-owners-gb300e/ refreshes them — if a unit count in tab 3 is edited by hand, the intervals go stale until then. "
     "xAI has no interval because Epoch publishes only a point estimate."],
    [],
    ["Table 1: EOY-2025 installed base by owner (GB300e). Mode = which GB300 spec the conversion divides by — dense FP8 FLOP/s, dense FP4 FLOP/s, or memory bandwidth — matching the toggle on the figure."],
    ["Owner", "FP8 mode — p10", "FP8 mode — median", "FP8 mode — p90",
     "FP4 mode — median", "BW mode — median", "Interval basis"],
]
for i, o in enumerate(US_OWNERS):
    rr = 8 + i
    e = mc[o]
    lo = round(e["modes"]["train_fp8"].get("lo", 0)) or ""
    hi = round(e["modes"]["train_fp8"].get("hi", 0)) or ""
    ov_vals.append([
        o, lo, f"={C}!F{subtotal_row[o]}", hi,
        f"={C}!G{subtotal_row[o]}", f"={C}!H{subtotal_row[o]}",
        "80% CI, Monte Carlo" if e["has_ci"] else "Point estimate — Epoch publishes no CI",
    ])
ov_vals.append([])
ov_vals.append([f"US total", "", f"=SUM(C8:C{7 + len(US_OWNERS)})", "", f"=SUM(E8:E{7 + len(US_OWNERS)})", f"=SUM(F8:F{7 + len(US_OWNERS)})",
                "No aggregated interval — per-owner intervals are not summed"])

# ================= create / rewrite spreadsheet =================
tok = token()
sid = None
for a in sys.argv[1:]:
    if a.startswith("--sid="):
        sid = a.split("=", 1)[1]
TITLE = "US AI Chip Owners — GB300e Conversions 2026-07-24"
TABS = ["1. Overview", "2. Chip specs & ratios", "3. Epoch counts & conversion"]
if sid is None:
    doc = api(tok, "POST", "https://sheets.googleapis.com/v4/spreadsheets", {
        "properties": {"title": TITLE},
        "sheets": [{"properties": {"title": t, "gridProperties": {"rowCount": 80, "columnCount": 12}}} for t in TABS],
    })
    sid = doc["spreadsheetId"]
    gids = {s["properties"]["title"]: s["properties"]["sheetId"] for s in doc["sheets"]}
else:
    doc = api(tok, "GET", f"https://sheets.googleapis.com/v4/spreadsheets/{sid}?fields=sheets(properties(sheetId,title))")
    gids = {s["properties"]["title"]: s["properties"]["sheetId"] for s in doc["sheets"]}

api(tok, "POST", f"https://sheets.googleapis.com/v4/spreadsheets/{sid}/values:batchUpdate", {
    "valueInputOption": "USER_ENTERED",
    "data": [
        {"range": "'1. Overview'!A1", "values": ov_vals},
        {"range": "'2. Chip specs & ratios'!A1", "values": specs_vals},
        {"range": "'3. Epoch counts & conversion'!A1", "values": conv_vals},
    ],
})

# formatting: bold headers + titles, wide columns, wrapped prose
fmt = []
def bold(tab, r0, r1, c0=0, c1=12):
    fmt.append({"repeatCell": {"range": {"sheetId": gids[tab], "startRowIndex": r0, "endRowIndex": r1,
        "startColumnIndex": c0, "endColumnIndex": c1},
        "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}}, "fields": "userEnteredFormat.textFormat.bold"}})
def width(tab, c0, c1, px):
    fmt.append({"updateDimensionProperties": {"range": {"sheetId": gids[tab], "dimension": "COLUMNS",
        "startIndex": c0, "endIndex": c1}, "properties": {"pixelSize": px}, "fields": "pixelSize"}})
def wrap(tab, r0, r1):
    fmt.append({"repeatCell": {"range": {"sheetId": gids[tab], "startRowIndex": r0, "endRowIndex": r1,
        "startColumnIndex": 0, "endColumnIndex": 1},
        "cell": {"userEnteredFormat": {"wrapStrategy": "WRAP", "verticalAlignment": "TOP"}},
        "fields": "userEnteredFormat.wrapStrategy,userEnteredFormat.verticalAlignment"}})

bold("1. Overview", 0, 1); bold("1. Overview", 5, 7); bold("1. Overview", 8 + len(US_OWNERS) + 1, 8 + len(US_OWNERS) + 2)
bold("2. Chip specs & ratios", 0, 1); bold("2. Chip specs & ratios", 5, 6)
bold("3. Epoch counts & conversion", 0, 1); bold("3. Epoch counts & conversion", 3, 4)
for o in US_OWNERS:
    bold("3. Epoch counts & conversion", subtotal_row[o] - 1, subtotal_row[o])
width("1. Overview", 0, 1, 340); width("1. Overview", 1, 7, 150)
width("2. Chip specs & ratios", 0, 1, 150); width("2. Chip specs & ratios", 1, 7, 160)
width("2. Chip specs & ratios", 7, 10, 170); width("2. Chip specs & ratios", 10, 11, 220)
width("3. Epoch counts & conversion", 0, 2, 150); width("3. Epoch counts & conversion", 2, 8, 160)
width("3. Epoch counts & conversion", 8, 9, 200)
wrap("1. Overview", 1, 4)
fmt.append({"repeatCell": {"range": {"sheetId": gids["1. Overview"], "startRowIndex": 1, "endRowIndex": 4},
    "cell": {"userEnteredFormat": {}}, "fields": "userEnteredFormat.wrapStrategy"}})
fmt.pop()  # keep wrap() effect only
# number formats: units + GB300e as #,##0
for tab, c0, c1, r0 in [("1. Overview", 1, 6, 7), ("3. Epoch counts & conversion", 2, 8, 4)]:
    fmt.append({"repeatCell": {"range": {"sheetId": gids[tab], "startRowIndex": r0, "endRowIndex": 70,
        "startColumnIndex": c0, "endColumnIndex": c1},
        "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "#,##0"}}},
        "fields": "userEnteredFormat.numberFormat"}})
api(tok, "POST", f"https://sheets.googleapis.com/v4/spreadsheets/{sid}:batchUpdate", {"requests": fmt})

# share with KP (work artifact default)
api(tok, "POST", f"https://www.googleapis.com/drive/v3/files/{sid}/permissions?sendNotificationEmail=false",
    {"type": "user", "role": "writer", "emailAddress": "konstantin@ctspolicy.org"})

print(f"https://docs.google.com/spreadsheets/d/{sid}/edit")
