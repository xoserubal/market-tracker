"""
Dev/test analysis for wiki/PREREGISTRO_CAPITULACION_PRECURSORES_V1.md.

Default run only touches DEV (events before the frozen cutoff date). Pass
--confirm-test to additionally evaluate, ONCE, whatever survived Bonferroni
in DEV plus the 7 frozen grid rules -- on TEST. Do not add new rules here
after seeing DEV results; edit the preregistration doc first if you do.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

HERE = Path(__file__).parent
EVENTS_PATH = HERE / "outputs" / "capitulation_events.jsonl"

CUTOFF = pd.Timestamp("2026-02-12")  # frozen in the preregistration: last 6 calendar months -> TEST

CONTINUOUS_FEATURES = [
    "rsi14_T0", "rsi14_delta_T-5_T0", "vol_ratio_max_T-2_T0",
    "down_day_streak_into_trough", "worst_single_day_pct_T-5_T0",
    "atr_pct_ratio_vs_avg60", "drop_pct", "days_peak_to_trough",
]
N_FEATURES = len(CONTINUOUS_FEATURES) + 1  # + bullish_divergence
BONFERRONI_ALPHA = 0.05 / N_FEATURES


def load():
    rows = [json.loads(l) for l in open(EVENTS_PATH)]
    df = pd.DataFrame(rows)
    df["trough_date"] = pd.to_datetime(df["trough_date"])
    df["split"] = np.where(df["trough_date"] >= CUTOFF, "test", "dev")
    return df


def mann_whitney(df, feature):
    a = df.loc[df["rebound"] == 1, feature].dropna()
    b = df.loc[df["rebound"] == 0, feature].dropna()
    if len(a) < 5 or len(b) < 5:
        return {"feature": feature, "n1": len(a), "n0": len(b), "note": "insufficient n"}
    u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
    # rank-biserial effect size
    effect = 1 - (2 * u) / (len(a) * len(b))
    return {
        "feature": feature, "n1": len(a), "n0": len(b),
        "median_rebound1": round(float(a.median()), 3),
        "median_rebound0": round(float(b.median()), 3),
        "p_value": round(float(p), 5),
        "rank_biserial_effect": round(float(effect), 3),
        "bonferroni_survives": bool(p < BONFERRONI_ALPHA),
    }


def fisher_divergence(df):
    sub = df.dropna(subset=["bullish_divergence"]).copy()
    if len(sub) < 10:
        return {"feature": "bullish_divergence", "note": "insufficient n"}
    sub["bullish_divergence"] = sub["bullish_divergence"].astype(bool)
    table = pd.crosstab(sub["bullish_divergence"], sub["rebound"])
    table = table.reindex(index=[True, False], columns=[1, 0], fill_value=0)
    odds, p = stats.fisher_exact(table.values)
    rate_true = sub.loc[sub["bullish_divergence"], "rebound"].mean() if (sub["bullish_divergence"]).any() else None
    rate_false = sub.loc[~sub["bullish_divergence"], "rebound"].mean() if (~sub["bullish_divergence"]).any() else None
    return {
        "feature": "bullish_divergence", "n_true": int((sub["bullish_divergence"]).sum()),
        "n_false": int((~sub["bullish_divergence"]).sum()),
        "rebound_rate_true": None if rate_true is None else round(float(rate_true), 3),
        "rebound_rate_false": None if rate_false is None else round(float(rate_false), 3),
        "p_value": round(float(p), 5),
        "bonferroni_survives": bool(p < BONFERRONI_ALPHA),
    }


# --- frozen grid, 7 rules (wiki/PREREGISTRO_CAPITULACION_PRECURSORES_V1.md) ---
def rule_masks(df):
    r1 = df["rsi14_T0"].between(30, 45)
    r2 = df["vol_ratio_max_T-2_T0"] >= 1.5
    r3 = df["down_day_streak_into_trough"] <= 1
    r4 = df["bullish_divergence"] == True  # noqa: E712
    r5 = df["atr_pct_ratio_vs_avg60"] >= 1.3
    return {
        "R1_rsi_moderate_30_45": r1,
        "R2_vol_spike_ge_1.5x": r2,
        "R3_fast_streak_le_1": r3,
        "R4_bullish_divergence": r4,
        "R5_atr_expansion_ge_1.3x": r5,
        "R6_R1_and_R2": r1 & r2,
        "R7_R2_and_R3": r2 & r3,
    }


def eval_rule(df, name, mask):
    mask = mask.fillna(False)
    n_in, n_out = int(mask.sum()), int((~mask).sum())
    if n_in < 10 or n_out < 10:
        return {"rule": name, "n_in": n_in, "n_out": n_out, "note": "insufficient n"}
    rate_in = df.loc[mask, "rebound"].mean()
    rate_out = df.loc[~mask, "rebound"].mean()
    table = pd.crosstab(mask, df["rebound"]).reindex(index=[True, False], columns=[1, 0], fill_value=0)
    _, p = stats.fisher_exact(table.values)
    return {
        "rule": name, "n_in": n_in, "n_out": n_out,
        "rebound_rate_in": round(float(rate_in), 3),
        "rebound_rate_out": round(float(rate_out), 3),
        "lift_pp": round(float((rate_in - rate_out) * 100), 1),
        "p_value": round(float(p), 5),
        "beats_base_rate_dev": bool(rate_in > rate_out and p < 0.05),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--confirm-test", action="store_true")
    args = ap.parse_args()

    df = load()
    dev = df[df["split"] == "dev"].copy()
    test = df[df["split"] == "test"].copy()

    print("=" * 70)
    print(f"DEV: {len(dev)} events ({(dev.trough_date.min().date())} -> "
          f"{(dev.trough_date.max().date())}), rebound rate = {dev.rebound.mean()*100:.1f}%")
    print(f"TEST: {len(test)} events ({(test.trough_date.min().date())} -> "
          f"{(test.trough_date.max().date())}), rebound rate = {test.rebound.mean()*100:.1f}%")
    print("=" * 70)

    print(f"\n--- Step 2: feature comparisons on DEV (Bonferroni alpha={BONFERRONI_ALPHA:.4f}) ---")
    dev_results = [mann_whitney(dev, f) for f in CONTINUOUS_FEATURES]
    dev_results.append(fisher_divergence(dev))
    survivors = []
    for r in dev_results:
        print(json.dumps(r))
        if r.get("bonferroni_survives"):
            survivors.append(r["feature"])
    print(f"\nSurvived Bonferroni in DEV: {survivors or 'NONE'}")

    print(f"\n--- Step 3: frozen 7-rule grid on DEV ---")
    masks = rule_masks(dev)
    rule_results = {}
    winning_rules = []
    for name, mask in masks.items():
        res = eval_rule(dev, name, mask)
        rule_results[name] = res
        print(json.dumps(res))
        if res.get("beats_base_rate_dev"):
            winning_rules.append(name)
    print(f"\nRules beating DEV base rate (p<0.05): {winning_rules or 'NONE'}")

    if not args.confirm_test:
        print("\n(run again with --confirm-test to check survivors/winning rules on TEST, once)")
        return

    print("\n" + "=" * 70)
    print("--- Step 4: ONE-SHOT confirmation on TEST ---")
    print("=" * 70)
    if not survivors and not winning_rules:
        print("Nothing survived DEV -> nothing to confirm. Conclusion: no reliable precursor found.")
        return

    for f in survivors:
        if f == "bullish_divergence":
            res = fisher_divergence(test)
        else:
            res = mann_whitney(test, f)
        print("TEST feature:", json.dumps(res))

    all_masks_test = rule_masks(test)
    for name in winning_rules:
        res = eval_rule(test, name, all_masks_test[name])
        print("TEST rule:", json.dumps(res))


if __name__ == "__main__":
    main()
