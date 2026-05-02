"""
Validacion del recession basket como metrica externa del framework.

Basket completo: DG, DLTR, WMT, MCD, KO, PG, JNJ, UNH, NEE, NEM
Sub-baskets:
  Deflacionario: KO, PG, JNJ, UNH, NEE, WMT
  Inflacionario: NEM, DG, DLTR, MCD, WMT
  Trade-down:    DG, DLTR, MCD, WMT  (KR excluido al no estar disponible)
"""

import pandas as pd
import numpy as np

RECESSION_BASKET     = ['DG', 'DLTR', 'WMT', 'MCD', 'KO', 'PG', 'JNJ', 'UNH', 'NEE', 'NEM']
BASKET_DEFLATIONARY  = ['KO', 'PG', 'JNJ', 'UNH', 'NEE', 'WMT']
BASKET_INFLATIONARY  = ['NEM', 'DG', 'DLTR', 'MCD', 'WMT']
BASKET_TRADE_DOWN    = ['DG', 'DLTR', 'MCD', 'WMT']
MIN_MEMBERS_REQUIRED = 7   # de 10 para el basket completo


def compute_basket_returns(
    prices_daily: pd.DataFrame,
    basket: list[str] | None = None,
    min_members: int | None  = None,
) -> pd.Series:
    """
    Retorno diario del basket = media equi-ponderada de retornos diarios.
    Solo se calcula si hay >= min_members tickers con dato ese dia.

    Returns Series diaria con retorno del basket (NaN si < min_members con dato).
    """
    if basket is None:
        basket = RECESSION_BASKET
    if min_members is None:
        # Escalar el minimo proporcionalmente al basket
        min_members = max(1, round(MIN_MEMBERS_REQUIRED * len(basket) / len(RECESSION_BASKET)))

    available = [t for t in basket if t in prices_daily.columns]
    if not available:
        return pd.Series(dtype=float)

    prices = prices_daily[available]
    returns = prices.pct_change()

    # Media solo donde hay suficientes miembros con dato
    valid_count = returns.notna().sum(axis=1)
    basket_ret  = returns.mean(axis=1)
    basket_ret[valid_count < min_members] = np.nan
    basket_ret.name = 'basket_return'
    return basket_ret


def compute_basket_forward_returns(
    prices_daily: pd.DataFrame,
    basket: list[str] | None = None,
    horizons_weeks: list[int] | None = None,
) -> pd.DataFrame:
    """
    Retornos forward del basket (media equi-ponderada del precio, no del retorno diario).
    Muestrea al viernes.

    Returns DataFrame indexado por fecha (viernes) con columnas:
      basket_price_t, basket_ret_fwd_4w, basket_ret_fwd_13w, basket_ret_fwd_26w
    """
    if basket is None:
        basket = RECESSION_BASKET
    if horizons_weeks is None:
        horizons_weeks = [4, 13, 26]

    available = [t for t in basket if t in prices_daily.columns]
    prices = prices_daily[available].resample('W-FRI').last()

    # Precio medio del basket
    valid_count = prices.notna().sum(axis=1)
    basket_price = prices.mean(axis=1)
    min_m = max(1, round(MIN_MEMBERS_REQUIRED * len(available) / len(RECESSION_BASKET)))
    basket_price[valid_count < min_m] = np.nan

    df = pd.DataFrame({'basket_price_t': basket_price})
    for nw in horizons_weeks:
        fwd = basket_price.shift(-nw)
        df[f'basket_ret_fwd_{nw}w'] = (fwd / basket_price) - 1.0
    return df


def find_regime_transitions(
    macro_history: pd.DataFrame,
    mode: str,
    to_regimes: list[str] | None = None,
) -> pd.DataFrame:
    """
    Identifica transiciones de regimen hacia Early Bear (Risk-OFF o Capitulacion).

    Returns DataFrame con columnas:
      transition_date, prev_regime, new_regime, mode, inflation_overlay_active
    """
    if to_regimes is None:
        to_regimes = ['Risk-OFF', 'Capitulacion']

    mh = macro_history[macro_history['mode'] == mode].sort_index()
    rows = []
    prev_regime = None

    for date, row in mh.iterrows():
        regime = row.get('regime')
        if pd.isna(regime):
            prev_regime = regime
            continue
        if prev_regime is not None and regime != prev_regime and regime in to_regimes:
            rows.append({
                'transition_date':        date,
                'prev_regime':            prev_regime,
                'new_regime':             regime,
                'mode':                   mode,
                'inflation_overlay_active': bool(row.get('flag_inflation_overlay', False)),
            })
        prev_regime = regime

    return pd.DataFrame(rows)


def build_recession_basket_validation(
    macro_history: pd.DataFrame,
    prices_daily: pd.DataFrame,
    spy_fwd: pd.DataFrame,
) -> pd.DataFrame:
    """
    Para cada transicion a Risk-OFF/Capitulacion, calcula alpha forward del basket completo
    y de los sub-baskets.

    spy_fwd: DataFrame indexado por fecha (viernes) con columnas ret_fwd_Nw para SPY.

    Returns DataFrame con una fila por transicion.
    """
    # Calcular retornos forward de cada basket
    baskets = {
        'full':         RECESSION_BASKET,
        'deflationary': BASKET_DEFLATIONARY,
        'inflationary': BASKET_INFLATIONARY,
        'trade_down':   BASKET_TRADE_DOWN,
    }
    basket_fwd = {}
    for name, blist in baskets.items():
        basket_fwd[name] = compute_basket_forward_returns(prices_daily, blist)

    rows = []
    for mode in ['A', 'B']:
        transitions = find_regime_transitions(macro_history, mode)
        for _, tr in transitions.iterrows():
            tdate = pd.Timestamp(tr['transition_date'])
            # Redondear a viernes mas cercano
            snap  = tdate + pd.offsets.Week(weekday=4) if tdate.weekday() != 4 else tdate
            if snap not in basket_fwd['full'].index:
                # Buscar viernes mas cercano disponible
                avail = basket_fwd['full'].index[basket_fwd['full'].index >= tdate]
                snap  = avail[0] if len(avail) else None
            if snap is None:
                continue

            row = {
                'transition_date':         tdate,
                'snap_date':               snap,
                'prev_regime':             tr['prev_regime'],
                'new_regime':              tr['new_regime'],
                'mode':                    mode,
                'inflation_overlay_active': tr['inflation_overlay_active'],
            }

            spy_row = spy_fwd.loc[snap] if snap in spy_fwd.index else None

            for nw in [4, 13, 26]:
                ret_col   = f'basket_ret_fwd_{nw}w'
                spy_col   = f'ret_fwd_{nw}w'
                # Basket completo
                b_ret  = float(basket_fwd['full'].loc[snap, ret_col]) if snap in basket_fwd['full'].index else np.nan
                spy_ret = float(spy_row[spy_col]) if spy_row is not None and spy_col in spy_row.index and not pd.isna(spy_row[spy_col]) else np.nan
                row[f'basket_return_{nw}w'] = b_ret
                row[f'basket_alpha_{nw}w']  = (b_ret - spy_ret) if not np.isnan(b_ret) and not np.isnan(spy_ret) else np.nan

            # Sub-basket alphas a 13w
            for name in ['deflationary', 'inflationary', 'trade_down']:
                b_ret_13 = float(basket_fwd[name].loc[snap, 'basket_ret_fwd_13w']) if snap in basket_fwd[name].index else np.nan
                spy_ret_13 = row.get('basket_return_13w', np.nan)  # reutilizar SPY
                spy_13 = float(spy_row['ret_fwd_13w']) if spy_row is not None and 'ret_fwd_13w' in spy_row.index and not pd.isna(spy_row['ret_fwd_13w']) else np.nan
                row[f'{name}_basket_alpha_13w'] = (b_ret_13 - spy_13) if not np.isnan(b_ret_13) and not np.isnan(spy_13) else np.nan

            # Falso positivo: basket underperforma SPY en las 4 semanas post-señal
            row['is_false_positive_4w'] = (
                not np.isnan(row.get('basket_alpha_4w', np.nan)) and
                row.get('basket_alpha_4w', 0) < 0
            )
            rows.append(row)

    return pd.DataFrame(rows)
