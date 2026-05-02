"""
Determinación de fit (activo líder en régimen actual).

Réplica de getEffectiveLeaders() en rotacion.html:

1. Obtener líderes por defecto del régimen (con histéresis ya en macro_history)
2. Aplicar TERM_PREMIUM_EXTREME: degradar régimen 1 nivel si flag activo
3. Aplicar conditional IWM: solo líder en Bull Pleno si HY<375 AND (curva>0 OR Δcurva>0)
4. Aplicar conditional oro (GC=F): solo líder si DFII10<1.0% OR DXY bajista 13w
5. Aplicar INFLATION_OVERLAY: TLT/QQQ/XLK pierden fit (salvo NetLiq Δ13w>300B);
   XLE/XLB/GC=F/SI=F se promueven

La función principal `get_effective_leaders` recibe una fila de macro y los valores
de DFII10 y DXY necesarios para los conditionals.
"""

from .clusters import REGIME_DEFAULT_LEADERS, degrade_regime


def get_effective_leaders(
    regime: str,
    hy_bps: float,
    t10y3m_pct: float,
    curve_d13w_pct: float,
    dfii10: float,
    dxy_ret_13w: float,
    flag_inflation: bool,
    netliq_d13w_b: float,
    flag_term_premium: bool,
) -> list[str]:
    """
    Devuelve la lista de líderes efectivos para el régimen y condiciones dadas.

    Args:
        regime:           nombre del régimen (ya con histéresis de macro_history)
        hy_bps:           HY spread en bps
        t10y3m_pct:       curva 10Y-3M en % (e.g. 0.56 para 56 bps)
        curve_d13w_pct:   delta 13w de la curva en % (positivo = steepening)
        dfii10:           tipos reales DFII10 en %
        dxy_ret_13w:      retorno DXY en % últimas 13 semanas (negativo = bajista)
        flag_inflation:   INFLATION_OVERLAY activo
        netliq_d13w_b:    NetLiq delta 13 semanas en billones USD
        flag_term_premium: TERM_PREMIUM_EXTREME activo
    """
    # Paso 1: régimen efectivo (TERM_PREMIUM_EXTREME degrada 1 nivel)
    effective_regime = degrade_regime(regime) if flag_term_premium else regime

    # Paso 2: líderes por defecto del régimen efectivo
    leaders = list(REGIME_DEFAULT_LEADERS.get(effective_regime, []))

    # Paso 3: conditional IWM (solo aplica si IWM está en la lista)
    if 'IWM' in leaders:
        iwm_ok = hy_bps < 375 and (t10y3m_pct > 0 or curve_d13w_pct > 0)
        if not iwm_ok:
            leaders = [t for t in leaders if t != 'IWM']

    # Paso 4: conditional oro (solo aplica si GC=F está en la lista)
    if 'GC=F' in leaders:
        gold_ok = dfii10 < 1.0 or dxy_ret_13w < 0
        if not gold_ok:
            leaders = [t for t in leaders if t != 'GC=F']

    # Paso 5: INFLATION_OVERLAY
    if flag_inflation:
        # Si NetLiq Δ13w > 300B, no bloquear TLT/QQQ/XLK
        if netliq_d13w_b <= 300:
            leaders = [t for t in leaders if t not in ('TLT', 'QQQ', 'XLK')]
        # Promover XLE/XLB/GC=F/SI=F como líderes
        for t in ('XLE', 'XLB', 'GC=F', 'SI=F'):
            if t not in leaders:
                leaders.append(t)

    return leaders


def determine_fit(ticker: str, effective_leaders: list[str]) -> bool:
    return ticker in effective_leaders
