"""
test_numeric_claims_validation.py
    — regression tests for the numeric-claim validator in paper_trading.py
      (_find_numeric_claims / _nearest_ticker / _is_numeric_discrepancy /
      _check_numeric_claims), added for the Semana 7 roadmap item
      "validación numérica automática". No pytest — same standalone-script
      convention as scripts/test_cava_mapping.py.

Every test here reproduces a specific false positive found while measuring
this validator against ~150 real historical entries in
docs/data/model_tests/ (an early version produced >1000 warnings on 130
selected items, almost all spurious — see the module docstring in
paper_trading.py for the full story). Run standalone:

  py -3 scripts/test_numeric_claims_validation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import paper_trading as pt  # noqa: E402

passed = 0
failed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed, failed
    if cond:
        passed += 1
    else:
        failed += 1
        print(f"FAIL: {name}" + (f" — {detail}" if detail else ""))


def claims(text: str) -> list[tuple[str, float, int]]:
    return pt._find_numeric_claims(text)


def has(cl: list[tuple[str, float, int]], field: str, value: float) -> bool:
    return any(f == field and abs(v - value) < 1e-6 for f, v, _ in cl)


# ── keyword-then-number ─────────────────────────────────────────────────
check("PCS 81.8 (keyword then number)", has(claims("CORZ shows PCS 81.8 today"), "pcs", 81.8))
check("PCS=80 (equals form)", has(claims("Selected over MARA (PCS=80)"), "pcs", 80.0))
check("rotation score of 8", has(claims("high rotation score of 8 here"), "rot_score", 8.0))
check("dems=15", has(claims("dems=15 confirms momentum"), "dems", 15.0))

# ── number-then-keyword ─────────────────────────────────────────────────
check("79.0 PCS (number then keyword)", has(claims("leader with 79.0 PCS and strong flow"), "pcs", 79.0))
check("35% 4-week return", has(claims("35% 4-week return outpaces peers"), "ret_4w_vs_spy", 35.0))

# ── streak phrasing (number-before-keyword, tight patterns) ────────────
check("12-week streak", has(claims("with a 12-week streak intact"), "streak_weeks", 12.0))
check("9 consecutive days streak",
      has(claims("shows 9 consecutive days streak of gains"), "streak_days", 9.0))

# ── regression: decimal point must not swallow a sentence-ending period ─
cl = claims("CORZ dems 16. Outperform_d10 9 superior to peers")
check("sentence-ending '16.' does not bridge into next sentence's keyword",
      not has(cl, "outperform_d10", 16.0),
      f"got claims={cl}")
check("but 'Outperform_d10 9' in the new sentence is still captured",
      has(cl, "outperform_d10", 9.0))

# ── regression: \n field separator must not be crossed by \s in gaps ────
cl = claims("Rotation score 7.0\nPCS below 85.0 strict threshold")
check("newline field separator blocks 7.0 pairing with the next field's PCS",
      not has(cl, "pcs", 7.0), f"got claims={cl}")
check("rot_score 7.0 from the first field is still captured correctly",
      has(cl, "rot_score", 7.0))

# ── _nearest_ticker: comparative mention in the same clause ─────────────
text = "Selected over MARA (PCS=80) because streak_weeks=12 vs MARA's 2"
cl = claims(text)
pcs_claim = next(c for c in cl if c[0] == "pcs")
subj = pt._nearest_ticker(text, pcs_claim[2], "ASTS", {"ASTS", "MARA"})
check("peer ticker in the same clause is correctly attributed", subj == "MARA", f"got subj={subj}")

# ── regression: ticker named in the PREVIOUS sentence must not leak forward ─
text = ("ASTS dems 19 exceeds MLX.AX dems 13 and CORZ dems 16. "
        "Outperform_d10 9 superior to peers.")
cl = claims(text)
od10_claims = [c for c in cl if c[0] == "outperform_d10"]
check("outperform_d10 9 exists in the new sentence", any(v == 9.0 for _, v, _ in od10_claims))
for _, v, off in od10_claims:
    if v == 9.0:
        subj = pt._nearest_ticker(text, off, "ASTS", {"ASTS", "MLX.AX", "CORZ"})
        check("own-ticker claim in a fresh sentence is NOT misattributed to "
              "a ticker named in the PREVIOUS sentence",
              subj == "ASTS", f"got subj={subj} (expected ASTS, not CORZ)")

# ── _is_numeric_discrepancy: tolerance + dist_52w_high sign handling ────
check("small rounding (81.8 vs 81.0) is not a discrepancy",
      not pt._is_numeric_discrepancy(81.8, 81.0))
check("small-scale field off-by-one within 0.5 abs is not a discrepancy",
      not pt._is_numeric_discrepancy(8.0, 7.6))
check("large relative miss on a return field IS a discrepancy",
      pt._is_numeric_discrepancy(40.65, 61.29))
check("dist_52w_high: sign-only mismatch is NOT a discrepancy",
      not pt._is_numeric_discrepancy(0.99, -0.99, field="dist_52w_high"))
check("dist_52w_high: genuine magnitude mismatch still IS a discrepancy",
      pt._is_numeric_discrepancy(6.0, -1.52, field="dist_52w_high"))
check("pcs field WITHOUT the dist_52w_high exemption: sign mismatch still flags",
      pt._is_numeric_discrepancy(8.0, -8.0))

# ── end-to-end: _check_numeric_claims produces a warning only for the ───
# ── real mismatch, not for the correctly-cited own-ticker numbers ───────
class _FakeResult:
    def __init__(self):
        self.soft_warnings: list[str] = []

    def warn(self, msg: str) -> None:
        self.soft_warnings.append(msg)


cand_by_ticker = {
    "CORZ": {"pcs": 81.0, "rot_score": 8.0, "dems": 8},
    "MARA": {"pcs": 80.0, "rot_score": 4.0},
}
r = _FakeResult()
pt._check_numeric_claims(
    r, "SELECT", "CORZ",
    "CORZ PCS 81.0 and rotation score of 8 comfortably clear MARA (PCS=80) and its rotation score of 4.",
    cand_by_ticker, {"CORZ", "MARA"},
)
check("end-to-end: no false warning when all cited numbers match payload exactly",
      len(r.soft_warnings) == 0, f"got warnings={r.soft_warnings}")

r2 = _FakeResult()
pt._check_numeric_claims(
    r2, "SELECT", "CORZ",
    "CORZ shows dems=19 today, well above the daily threshold.",
    cand_by_ticker, {"CORZ", "MARA"},
)
check("end-to-end: real mismatch (dems 19 cited vs 8 actual) produces exactly one warning",
      len(r2.soft_warnings) == 1, f"got warnings={r2.soft_warnings}")

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
