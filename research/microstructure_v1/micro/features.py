"""Variables de G2 (G2A_PROTOCOLO §3 + enmiendas). Funciones puras sobre la serie de UNA entidad, ordenada por fecha y
ajustada hacia atrás por splits (enmienda 4.4: equivalente a ajustar solo con splits <= t, porque todas las variables
son cocientes dentro de su ventana).

Entradas por día (DataFrame `s`, una fila por sesión con negociación del valor):
  date, o, h, l, c, v (barra diaria oficial ajustada), er (eficiencia del recorrido intradía, de los minutos),
  y aparte `vap`: matriz días × celdas de volumen por precio en la rejilla de log-precio ajustada.
Ninguna función mira datos posteriores a la fila que calcula.
"""
import math

import numpy as np
import pandas as pd

LOG_STEP = math.log(1.0025)
NORM = 120          # normalización frente a la historia propia
PERSIST = 20        # ventana de persistencia
C2_WIN = 10         # media reciente de la actividad sin desplazamiento
POC_RECENT = 10     # POC reciente para la migración
EPS_DESP = 0.05


def pct_prev(x: np.ndarray, n: int = NORM) -> np.ndarray:
    """Percentil de x[i] entre x[i-n..i-1]: (nº < x + 0,5 · nº =) / n. Vacío si falta alguno."""
    x = np.asarray(x, float)
    out = np.full(len(x), np.nan)
    if len(x) <= n:
        return out
    w = np.lib.stride_tricks.sliding_window_view(x[:-1], n)          # w[j] = x[j..j+n-1], previos de x[j+n]
    cur = x[n:]
    ok = ~np.isnan(w).any(axis=1) & ~np.isnan(cur)
    lt = (w < cur[:, None]).sum(axis=1)
    eq = (w == cur[:, None]).sum(axis=1)
    out[n:] = np.where(ok, (lt + 0.5 * eq) / n, np.nan)
    return out


def prev_median(x: np.ndarray, n: int = NORM) -> np.ndarray:
    """Mediana de x[i-n..i-1]."""
    return pd.Series(x).shift(1).rolling(n, min_periods=n).median().to_numpy()


def wilder_atr(h, l, c, n=14):
    h, l, c = map(lambda a: np.asarray(a, float), (h, l, c))
    tr = np.maximum(h - l, np.maximum(np.abs(h - np.r_[np.nan, c[:-1]]), np.abs(l - np.r_[np.nan, c[:-1]])))
    tr[0] = h[0] - l[0]
    atr = np.full(len(c), np.nan)
    if len(c) < n:
        return atr
    atr[n - 1] = np.nanmean(tr[:n])
    for i in range(n, len(c)):
        atr[i] = (atr[i - 1] * (n - 1) + tr[i]) / n
    return atr


def awd(s: pd.DataFrame, intraday_skip=None) -> pd.DataFrame:
    """Actividad sin desplazamiento por sesión, variantes diaria e intradía, y su percentil propio.

    intraday_skip: máscara de días de caída de datos de minuto (enmienda 8). Para la variante intradía no son sesión:
    la mediana de ER y el percentil se calculan sobre las sesiones intradía válidas; en esos días awd_i queda vacío.
    """
    v, c = s["v"].to_numpy(float), s["c"].to_numpy(float)
    r = np.r_[np.nan, np.log(c[1:] / c[:-1])]
    rv = v / prev_median(v)
    desp_d = np.abs(r) / prev_median(np.abs(r))
    er = s["er"].to_numpy(float)
    keep = np.ones(len(er), bool) if intraday_skip is None else ~np.asarray(intraday_skip, bool)
    a_i = np.full(len(er), np.nan)
    p_i = np.full(len(er), np.nan)
    er_k = er[keep]
    with np.errstate(divide="ignore", invalid="ignore"):
        a_d = np.log(rv) - np.log(desp_d + EPS_DESP)
        a_k = np.log(rv[keep]) - np.log(er_k / prev_median(er_k) + EPS_DESP)
    a_i[keep] = a_k
    p_i[keep] = pct_prev(a_k)
    return pd.DataFrame({"rv": rv, "awd_d": a_d, "awd_i": a_i, "p_awd_d": pct_prev(a_d), "p_awd_i": p_i},
                        index=s.index)


def roll_mean(x, n):
    return pd.Series(x).rolling(n, min_periods=n).mean().to_numpy()


def value_area(hist: np.ndarray, frac: float = 0.70):
    """(índice del POC, nº de celdas del área de valor contigua) ampliando hacia el lado con más volumen."""
    tot = hist.sum()
    if tot <= 0:
        return -1, 0
    poc = int(np.argmax(hist))
    lo = hi = poc
    acc = hist[poc]
    n = len(hist)
    while acc < frac * tot:
        left = hist[lo - 1] if lo > 0 else -1.0
        right = hist[hi + 1] if hi < n - 1 else -1.0
        if right > left:
            hi += 1
            acc += right
        else:
            lo -= 1
            acc += left
    return poc, hi - lo + 1


def vap_window_stats(vap: np.ndarray, bin0: int, c: np.ndarray, h: np.ndarray, l: np.ndarray, L: int):
    """Por fecha i (ventana i-L+1..i): VAW_L, posición del POC_L y del POC_10 en el rango de cierres de L sesiones.

    vap: matriz días × celdas (rejilla ajustada); bin0 = índice de celda de la columna 0.
    """
    nd = len(c)
    cs = np.cumsum(np.vstack([np.zeros(vap.shape[1]), vap]), axis=0)
    vaw = np.full(nd, np.nan)
    pos_l = np.full(nd, np.nan)
    pos_10 = np.full(nd, np.nan)
    for i in range(L - 1, nd):
        win = cs[i + 1] - cs[i + 1 - L]
        poc, width = value_area(win)
        if poc < 0:
            continue
        hi, lo = np.max(h[i - L + 1:i + 1]), np.min(l[i - L + 1:i + 1])
        if hi > lo:
            vaw[i] = min(1.0, width * LOG_STEP / math.log(hi / lo))
        cmax, cmin = np.max(c[i - L + 1:i + 1]), np.min(c[i - L + 1:i + 1])
        rec = cs[i + 1] - cs[i + 1 - POC_RECENT]
        if cmax > cmin:
            p_l = math.exp((bin0 + poc + 0.5) * LOG_STEP)
            p_10 = math.exp((bin0 + int(np.argmax(rec)) + 0.5) * LOG_STEP)
            pos_l[i] = (p_l - cmin) / (cmax - cmin)
            pos_10[i] = (p_10 - cmin) / (cmax - cmin)
    return vaw, pos_l, pos_10


def family_c(s: pd.DataFrame, vap: np.ndarray, bin0: int, a: pd.DataFrame, L: int, thetas=(0.80, 0.90)):
    """RANGO_L, componentes C1-C4 e índice AI_t para cada θ."""
    c, h, l = (s[x].to_numpy(float) for x in ("c", "h", "l"))
    atr = wilder_atr(h, l, c)
    rng = (pd.Series(c).rolling(L, min_periods=L).max() - pd.Series(c).rolling(L, min_periods=L).min()).to_numpy()
    vaw, pos_l, pos_10 = vap_window_stats(vap, bin0, c, h, l, L)
    c1 = 1 - vaw
    c2 = roll_mean(a["p_awd_d"].to_numpy(), C2_WIN)
    c4 = pos_10 - pos_l
    out = {f"range_{L}": rng / atr, f"c1_{L}": c1, f"c4_{L}": c4, "c2": c2}
    p1, p2, p4 = pct_prev(c1), pct_prev(c2), pct_prev(c4)
    for th in thetas:
        flags = np.where(np.isnan(a["p_awd_d"].to_numpy()), np.nan, (a["p_awd_d"].to_numpy() >= th).astype(float))
        c3 = roll_mean(flags, PERSIST)
        out[f"c3_{int(th * 100)}"] = c3
        out[f"ai_{L}_{int(th * 100)}"] = (p1 + p2 + pct_prev(c3) + p4) / 4
    return pd.DataFrame(out, index=s.index)


def momentum_filters(s: pd.DataFrame, spy_c: pd.Series):
    """Fuerza relativa 63 frente al SPY, máximo de 252 en las últimas 20, momentum 5/20, extensión SMA20/ATR."""
    c = s["c"].to_numpy(float)
    dates = s["date"].to_numpy()
    spy = spy_c.reindex(dates).to_numpy(float)
    with np.errstate(divide="ignore", invalid="ignore"):
        rs63 = np.r_[np.full(63, np.nan), np.log(c[63:] / c[:-63]) - np.log(spy[63:] / spy[:-63])]
        mom5 = np.r_[np.full(5, np.nan), c[5:] / c[:-5] - 1]
        mom20 = np.r_[np.full(20, np.nan), c[20:] / c[:-20] - 1]
    m252 = pd.Series(c).rolling(252, min_periods=252).max().to_numpy()
    is_hi = (c >= m252).astype(float)
    is_hi[np.isnan(m252)] = np.nan
    hi_last20 = pd.Series(is_hi).rolling(20, min_periods=20).max().to_numpy()
    atr = wilder_atr(s["h"], s["l"], s["c"])
    ext = (c - pd.Series(c).rolling(20, min_periods=20).mean().to_numpy()) / atr
    return pd.DataFrame({"rs63_spy": rs63, "high252_last20": hi_last20, "mom5": mom5, "mom20": mom20,
                         "ext_sma20_atr": ext, "atr": atr}, index=s.index)
