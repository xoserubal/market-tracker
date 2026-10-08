# Fase 2 — informe de calibración DIY vs ZeroGEX

Generado: 2026-10-08T12:41:29.909355-04:00
Total snapshots: 36  |  Símbolos: QQQ, SPX

## QQQ — 18 sesión(es)
- median_abs_flip_diff: 1.60
- p90_abs_flip_diff: 5.40
- regime_agreement_rate: 71.4% (n=7)
- near_flip_agreement: 100.0% (n=5 sesiones con al menos una fuente en transition)
- bias_stability: mean=1.68 stdev=4.55
  serie completa (diy_flip - zerogex_flip): [-1.13, -3.7, -1.75, 1.08, 0.53, 15.72, 4.25, 2.9, 2.41, -0.62, -0.34, -1.45, 0.84, 6.54, 3.0, -1.43]

### Detalle por sesión
| Fecha | Market Spot | DIY Flip | DIY Bucket | ZeroGEX Flip | ZeroGEX Bucket | Abs Diff |
|---|---:|---:|---|---:|---|---:|
| 2026-09-14 | 709.18 | 716.6 | negative_gamma | 717.7 | uncertain | 1.13 |
| 2026-09-15 | 704.54 | 713.7 | negative_gamma | 717.4 | uncertain | 3.70 |
| 2026-09-16 | 704.72 | 713.0 | negative_gamma | 714.7 | uncertain | 1.75 |
| 2026-09-17 | 716.92 | 716.3 | transition | 715.3 | transition | 1.08 |
| 2026-09-18 | 721.45 | 718.3 | transition | 717.8 | positive_gamma | 0.53 |
| 2026-09-21 | 741.47 | 721.4 | positive_gamma | n/a | uncertain | n/a |
| 2026-09-22 | 747.46 | 737.4 | positive_gamma | n/a | uncertain | n/a |
| 2026-09-23 | 741.21 | 746.9 | negative_gamma | 731.2 | positive_gamma | 15.72 |
| 2026-09-24 | 741.10 | 742.2 | transition | 737.9 | uncertain | 4.25 |
| 2026-09-25 | 744.50 | 738.9 | positive_gamma | 736.0 | positive_gamma | 2.90 |
| 2026-09-28 | 736.53 | 739.7 | transition | 737.2 | uncertain | 2.41 |
| 2026-09-29 | 737.93 | 736.1 | transition | 736.7 | transition | 0.62 |
| 2026-09-30 | 739.77 | 739.2 | transition | 739.6 | transition | 0.34 |
| 2026-10-01 | 742.03 | 740.7 | transition | 742.2 | uncertain | 1.45 |
| 2026-10-02 | 749.58 | 743.5 | positive_gamma | 742.7 | uncertain | 0.84 |
| 2026-10-05 | 756.20 | 748.5 | positive_gamma | 742.0 | uncertain | 6.54 |
| 2026-10-06 | 759.66 | 753.6 | positive_gamma | 750.6 | uncertain | 3.00 |
| 2026-10-07 | 757.73 | 756.4 | transition | 757.8 | transition | 1.43 |

**VEREDICTO QQQ:** regime_agreement_rate=71.4% < 85.0% → DIY no replica. Si ZeroGEX pasó Fase 1 (sí, para ambos símbolos) → decisión de juicio con el usuario: mantener suscripción para este símbolo, o descartarlo (sección 2.3).

## SPX — 18 sesión(es)
- median_abs_flip_diff: 24.55
- p90_abs_flip_diff: 91.52
- regime_agreement_rate: n/a (0 sesiones comparables)
- near_flip_agreement: n/a (ninguna sesión cerca del flip todavía)
- bias_stability: mean=68.41 stdev=246.34
  serie completa (diy_flip - zerogex_flip): [-10.64, -83.75, -40.92, -11.72, 24.62, 65.35, 77.79, 16.64, 3.96, 24.49, 5.4, -14.32, -26.52, -14.59, 13.28, 1038.66, 109.65, 53.97]

### Detalle por sesión
| Fecha | Market Spot | DIY Flip | DIY Bucket | ZeroGEX Flip | ZeroGEX Bucket | Abs Diff |
|---|---:|---:|---|---:|---|---:|
| 2026-09-14 | 7619.98 | 7670.8 | negative_gamma | 7681.5 | uncertain | 10.64 |
| 2026-09-15 | 7585.73 | 7640.3 | negative_gamma | 7724.0 | uncertain | 83.75 |
| 2026-09-16 | 7551.81 | 7633.8 | negative_gamma | 7674.7 | uncertain | 40.92 |
| 2026-09-17 | 7637.76 | 7642.7 | transition | 7654.4 | uncertain | 11.72 |
| 2026-09-18 | 7650.50 | 7675.3 | transition | 7650.7 | uncertain | 24.62 |
| 2026-09-21 | 7764.70 | 7658.8 | positive_gamma | 7593.4 | uncertain | 65.35 |
| 2026-09-22 | 7764.64 | 7701.6 | positive_gamma | 7623.8 | uncertain | 77.79 |
| 2026-09-23 | 7706.03 | 7701.3 | transition | 7684.7 | uncertain | 16.64 |
| 2026-09-24 | 7704.13 | 7701.6 | transition | 7697.6 | uncertain | 3.96 |
| 2026-09-25 | 7743.41 | 7704.8 | transition | 7680.3 | uncertain | 24.49 |
| 2026-09-28 | 7683.69 | 7707.2 | transition | 7701.8 | uncertain | 5.40 |
| 2026-09-29 | 7670.84 | 7694.9 | transition | 7709.2 | uncertain | 14.32 |
| 2026-09-30 | 7651.54 | 7668.3 | transition | 7694.8 | uncertain | 26.52 |
| 2026-10-01 | 7666.45 | 7684.1 | transition | 7698.7 | uncertain | 14.59 |
| 2026-10-02 | 7722.72 | 7680.5 | positive_gamma | 7667.2 | uncertain | 13.28 |
| 2026-10-05 | 7773.95 | 8699.6 | negative_gamma | 7660.9 | uncertain | 1038.66 |
| 2026-10-06 | 7818.93 | 7741.9 | positive_gamma | 7632.3 | uncertain | 109.65 |
| 2026-10-07 | 7801.77 | 7750.6 | positive_gamma | 7696.6 | uncertain | 53.97 |

**VEREDICTO SPX:** pendiente — faltan sesiones (mínimo 10, hay 18).
