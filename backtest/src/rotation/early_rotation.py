"""
Gestión del estado early_rotation_candidates (streaks por activo).

Tres condiciones para emitir ROT. TEMPRANA (todas obligatorias):
  1. Persistencia individual: RotScore ≥ 8 durante ≥3 semanas consecutivas
  2. Clúster categorial:      ≥2 activos del mismo clúster con streak ≥3
  3. Filtro benchmark:        SPY > SMA200  OR  Δ13w NetLiq > +300B

Estado persistido: dict {ticker: {'streak': int, 'last_score': float|None}}
"""

from .clusters import CLUSTERS, get_cluster

STREAK_THRESHOLD = 3
SCORE_THRESHOLD  = 8.0


def update_streak(ticker: str, score: float | None, state: dict) -> dict:
    """
    Actualiza el streak de un ticker en el estado early_rotation.

    Regla: si score ≥ 8 → streak += 1; si no → streak = 0.
    """
    entry = state.get(ticker, {'streak': 0, 'last_score': None})
    if score is not None and score >= SCORE_THRESHOLD:
        entry['streak'] = entry.get('streak', 0) + 1
    else:
        entry['streak'] = 0
    entry['last_score'] = score
    state[ticker] = entry
    return state


def evaluate_early_rotation(
    ticker: str,
    fit: bool,
    state: dict,
    spy_above_sma200: bool | None,
    netliq_d13w_b: float | None,
) -> dict:
    """
    Evalúa si un activo califica para ROT. TEMPRANA.

    Returns:
        {
          'is_early_rotation':      bool,
          'cluster':                str | None,
          'cluster_qualifying_peers': list[str],
          'benchmark_condition':    'spy_above_sma200' | 'netliq_expanding' | None,
          'er_validated_by_netliq': bool,
        }
    """
    base = {
        'is_early_rotation': False,
        'cluster': None,
        'cluster_qualifying_peers': [],
        'benchmark_condition': None,
        'er_validated_by_netliq': False,
    }

    # ROT. TEMPRANA requiere que el activo NO tenga fit con el régimen actual
    if fit:
        return base

    # Condición 1: persistencia individual streak ≥ 3
    entry = state.get(ticker, {'streak': 0})
    if entry.get('streak', 0) < STREAK_THRESHOLD:
        return base

    # Condición 3: benchmark (evaluar antes que clúster, más barato)
    spy_ok    = spy_above_sma200 is True
    netliq_ok = (netliq_d13w_b is not None and netliq_d13w_b > 300)
    if not spy_ok and not netliq_ok:
        return base

    # Condición 2: clúster ≥2 miembros con streak ≥ 3
    cluster = get_cluster(ticker)
    if cluster is None:
        return base

    qualifying = [
        t for t in CLUSTERS[cluster]
        if state.get(t, {}).get('streak', 0) >= STREAK_THRESHOLD
    ]
    if len(qualifying) < 2:
        return base

    # Determinar vía de benchmark
    if spy_ok:
        benchmark = 'spy_above_sma200'
        via_netliq = False
    else:
        benchmark = 'netliq_expanding'
        via_netliq = True

    return {
        'is_early_rotation':        True,
        'cluster':                  cluster,
        'cluster_qualifying_peers': [t for t in qualifying if t != ticker],
        'benchmark_condition':      benchmark,
        'er_validated_by_netliq':   via_netliq,
    }
