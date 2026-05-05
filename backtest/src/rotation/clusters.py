"""
Universo, clústeres y tabla de fit por régimen.
Réplica exacta de rotacion.html (UNIVERSE, CLUSTERS, REGIMES.defaultLeaders).
"""

UNIVERSE = [
    'XLK', 'XLC', 'XLY', 'XLF', 'XLI', 'XLB', 'XLE',
    'XLV', 'XLRE', 'XLP', 'XLU',
    'SPY',
    'QQQ', 'IWM', 'EEM', 'EFA', 'FEZ', 'TLT',
    'GC=F', 'SI=F', 'BZ=F', 'HG=F', 'BTC-USD',
]

TICKERS_NO_SPY = [t for t in UNIVERSE if t != 'SPY']

CLUSTERS = {
    'Growth':         ['XLK', 'XLC', 'XLY', 'QQQ', 'BTC-USD'],
    'Value/Cyclical': ['XLF', 'XLI', 'XLB', 'XLE'],
    'Defensive':      ['XLP', 'XLU', 'XLV', 'XLRE'],
    'Duration':       ['TLT'],          # un solo miembro → nunca dispara (intencional)
    'Commodities':    ['GC=F', 'SI=F', 'BZ=F', 'HG=F'],
    'Small/EM':       ['IWM', 'EEM', 'EFA', 'FEZ'],
}

# Líderes por defecto de cada régimen (sin conditionals aplicados)
REGIME_DEFAULT_LEADERS = {
    'Bull Pleno':   ['XLK', 'XLC', 'XLY', 'QQQ', 'BTC-USD', 'IWM', 'EEM', 'EFA', 'FEZ'],
    'Bull Maduro':  ['XLF', 'XLI', 'XLB', 'XLE', 'GC=F', 'SI=F', 'BZ=F', 'HG=F'],
    'Transición':   ['XLP', 'XLU', 'XLV', 'XLRE', 'GC=F', 'TLT'],
    'Risk-OFF':     ['TLT', 'GC=F', 'XLP', 'XLU'],
    'Capitulación': ['TLT', 'GC=F'],
}

REGIME_ORDER = ['Bull Pleno', 'Bull Maduro', 'Transición', 'Risk-OFF', 'Capitulación']


def get_cluster(ticker: str) -> str | None:
    for name, members in CLUSTERS.items():
        if ticker in members:
            return name
    return None


def degrade_regime(regime_label: str) -> str:
    """Degrada un régimen un nivel (usado por TERM_PREMIUM_EXTREME)."""
    idx = REGIME_ORDER.index(regime_label) if regime_label in REGIME_ORDER else -1
    if idx < 0:
        return regime_label
    return REGIME_ORDER[min(idx + 1, len(REGIME_ORDER) - 1)]


def compute_cluster_health(
    cluster_name: str,
    members: list[str],
    scores: dict[str, float | None],
    returns: dict[str, dict],
    date,
) -> dict:
    """
    Calcula métricas agregadas de salud para un clúster en una fecha.

    Args:
        scores:  {ticker: rot_score} — None si no hay datos
        returns: {ticker: {'ret_2w_vs_spy': ..., 'ret_4w_vs_spy': ..., 'ret_13w_vs_spy': ...}}
    """
    valid_scores = [scores[t] for t in members if t in scores and scores[t] is not None]
    n_total = len(members)
    n_valid = len(valid_scores)

    avg_score = sum(valid_scores) / n_valid if n_valid else None
    pct_ge7   = sum(1 for s in valid_scores if s >= 7) / n_valid if n_valid else None
    pct_ge8   = sum(1 for s in valid_scores if s >= 8) / n_valid if n_valid else None

    def _pct_positive(key):
        vals = [returns[t][key] for t in members
                if t in returns and returns[t].get(key) is not None]
        if not vals:
            return None
        return sum(1 for v in vals if v > 0) / len(vals)

    def _avg(key):
        vals = [returns[t][key] for t in members
                if t in returns and returns[t].get(key) is not None]
        return sum(vals) / len(vals) if vals else None

    return {
        'cluster':                    cluster_name,
        'n_members':                  n_total,
        'n_members_with_data':        n_valid,
        'avg_rotation_score':         avg_score,
        'pct_members_score_ge_7':     pct_ge7,
        'pct_members_score_ge_8':     pct_ge8,
        'pct_ret_2w_positive_vs_spy': _pct_positive('ret_2w_vs_spy'),
        'pct_ret_4w_positive_vs_spy': _pct_positive('ret_4w_vs_spy'),
        'pct_ret_13w_positive_vs_spy':_pct_positive('ret_13w_vs_spy'),
        'avg_ret_4w_vs_spy':          _avg('ret_4w_vs_spy'),
        'avg_ret_13w_vs_spy':         _avg('ret_13w_vs_spy'),
    }
