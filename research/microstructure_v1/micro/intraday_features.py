"""Medidas intradía a partir de barras de 1 minuto, normalizadas frente a la historia del propio valor (E1, cat-v0).

Diseño
- Cada sesión se representa como una fila de 960 minutos (04:00-20:00 NY). Los tramos salen del calendario de cada
  día (sessions.bounds), así que los cierres anticipados y el cambio de hora no desalinean nada.
- Perfil propio (solo sesiones de la línea base, estrictamente anteriores): volumen esperado por minuto (la
  negociación continua alineada desde la apertura; premercado y after hours por hora de reloj), sigma robusta de los
  retornos de 1 minuto por bloques de 30 minutos, tamaño medio por operación y rango típico de una vela.
- Cada medida diaria es un EXTREMO del día (máximo de una serie por minuto) o un valor en un instante fijo (cierre,
  apertura, +30 min de after hours). Se compara con el MISMO estadístico de las sesiones de la línea base. Comparar
  extremos con extremos tiene en cuenta que se examinan cientos de minutos: no es un umbral por minuto.
- Las sesiones de la línea base se normalizan con el mismo perfil que el día evaluado (todo anterior a él). Ese
  perfil incluye a cada sesión de la base; con 60 sesiones su efecto sobre la mediana es despreciable y evita
  recalcular en cascada. Nada usa datos posteriores al día evaluado.
- Las dos barras mixtas (apertura y cierre) no entran en las medidas de negociación continua. Las medidas que solo se
  pueden estimar con barras llevan `estimated=True` y se detallan con trades en el desglose.
- Sin divisiones inestables: los denominadores de volumen tienen un suelo; I1/I2 no son cocientes sino condiciones
  conjuntas; la eficiencia direccional exige un recorrido mínimo.
"""
import warnings
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import sessions, test_guard
from .manifest import Manifest

D1_WINDOWS = (1, 5, 15, 30)
V1_WINDOWS = (1, 5, 15)
C1_WINDOWS = (5, 10, 30)
C3_WINDOWS = (30, 60)
P2_WINDOWS = (30, 60)
BUCKET = 30
VOL_FLOOR_SHARE = 0.05          # suelo del volumen esperado por minuto: 5 % de la mediana de la negociación continua
SIGMA_FLOOR = 1e-5
MIN_TRADES_SIZE = 20            # V2: operaciones mínimas en la ventana para hablar de tamaño medio
THIN_VOL_RATIO = 1.0            # I1: volumen de la ventana como mucho el esperado
STALL_Z = 0.5                   # I2: desplazamiento como mucho 0,5 sigmas
HIGH_VOL_MULT = 2.0             # P3: volumen al menos el doble del esperado
POST_EXT_MIN = 35               # C3: recorrido máximo en los primeros 35 min de after hours
NY = sessions.NY


# ── carga de barras ──
def load_bars(symbol: str, days: list, manifest: Manifest = None) -> pd.DataFrame:
    """Barras de 1 minuto del símbolo en esos días (todas las unidades 'ok', mensuales o diarias, cualquier asof).

    Las fechas reservadas del periodo de prueba se descartan nada más leer (el llamante ya debería haberlas quitado)."""
    days = set(test_guard.allowed(days))
    if not days:
        return pd.DataFrame(columns=["t", "o", "h", "l", "c", "v", "n", "vw"])
    months = {d[:7] for d in days}
    m = manifest or Manifest()
    rows = [r for r in m.rows("kind='bars' AND symbol=? AND status='ok'", (symbol,))
            if r["period"] in days or r["period"] in months]
    frames = []
    for r in rows:
        f = pd.read_parquet(r["path"], columns=["t", "o", "h", "l", "c", "v", "n", "vw"])
        f["t"] = pd.to_datetime(f["t"], utc=True)
        f["_unit"] = r["unit_key"]
        frames.append(f)
    if not frames:
        return pd.DataFrame(columns=["t", "o", "h", "l", "c", "v", "n", "vw", "_unit"])
    b = pd.concat(frames, ignore_index=True)
    b["_day"] = b["t"].dt.tz_convert(NY).dt.strftime("%Y-%m-%d")
    b = b[b["_day"].isin(days)]
    return b.drop_duplicates("t", keep="first").sort_values("t").reset_index(drop=True)


@dataclass
class DayMatrix:
    days: list
    meta: list
    O: np.ndarray
    H: np.ndarray
    L: np.ndarray
    C: np.ndarray
    V: np.ndarray
    N: np.ndarray
    VW: np.ndarray
    units: dict = field(default_factory=dict)

    def idx(self, day):
        return self.days.index(day)


def build_matrix(bars: pd.DataFrame, days: list) -> DayMatrix:
    D, S = len(days), sessions.N_SLOTS
    arr = {k: np.full((D, S), np.nan) for k in ("O", "H", "L", "C", "V", "N", "VW")}
    meta, units = [], {}
    for i, d in enumerate(days):
        b = sessions.bounds(d)
        meta.append(b)
        x = bars[bars["_day"] == d] if len(bars) else bars
        if not len(x):
            continue
        s = sessions.slots_of(x["t"], b)
        ok = (s >= 0) & (s < S)
        for k, col in (("O", "o"), ("H", "h"), ("L", "l"), ("C", "c"), ("V", "v"), ("N", "n"), ("VW", "vw")):
            arr[k][i, s[ok]] = x[col].to_numpy(dtype=float)[ok]
        units[d] = sorted(set(x["_unit"]))
    return DayMatrix(days=list(days), meta=meta, units=units, **arr)


# ── utilidades ──
def _ffill(a: np.ndarray) -> np.ndarray:
    """Último precio conocido dentro de la sesión (NaN antes de la primera barra)."""
    return pd.Series(a).ffill().to_numpy()


def _rsum(x: np.ndarray, k: int) -> np.ndarray:
    """Suma móvil de k elementos que termina en cada posición (NaN -> 0); NaN en las k-1 primeras."""
    c = np.concatenate([[0.0], np.cumsum(np.nan_to_num(x))])
    out = np.full(len(x), np.nan)
    out[k - 1:] = c[k:] - c[:-k]
    return out


def _rcount(mask: np.ndarray, k: int) -> np.ndarray:
    return _rsum(mask.astype(float), k)


def _robust_sigma(r: np.ndarray) -> float:
    r = r[np.isfinite(r)]
    if len(r) < 10:
        return np.nan
    mad = np.median(np.abs(r - np.median(r))) * 1.4826
    s = mad if mad > 0 else float(np.std(r))
    return max(s, SIGMA_FLOOR)


def _runs(flag: np.ndarray) -> np.ndarray:
    out = np.zeros(len(flag))
    c = 0
    for i, f in enumerate(flag):
        c = c + 1 if f else 0
        out[i] = c
    return out


# ── perfil propio ──
@dataclass
class Profile:
    vol_cont: np.ndarray      # por minutos desde la apertura (0 = barra mixta de apertura)
    vol_pre: np.ndarray       # por minuto de reloj (slot)
    vol_post: np.ndarray      # por minutos desde el cierre (0 = barra mixta de cierre)
    sig_cont: np.ndarray      # por bloque de 30 min desde la apertura
    sig_pre: float
    sig_post: float
    size_cont: np.ndarray     # tamaño medio por operación, por bloque
    range_cont: np.ndarray    # (máx - mín) / cierre de una vela, por bloque
    vol_floor: float
    n_days: int


def build_profile(M: DayMatrix, rows: list) -> Profile:
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return _build_profile(M, rows)


def _build_profile(M: DayMatrix, rows: list) -> Profile:
    S = sessions.N_SLOTS
    vc, vp, vq = np.full((len(rows), S), np.nan), np.full((len(rows), S), np.nan), np.full((len(rows), S), np.nan)
    rc, rpre, rpost, sz, rg = {}, [], [], {}, {}
    for j, i in enumerate(rows):
        b = M.meta[i]
        o, c, e = b["open_slot"], b["close_slot"], b["end_slot"]
        v = np.nan_to_num(M.V[i])
        vc[j, :c - o] = v[o:c]
        vp[j, :o] = v[:o]
        vq[j, :e - c] = v[c:e]
        lc = np.log(_ffill(M.C[i]))
        r = np.diff(lc, prepend=np.nan)
        has = ~np.isnan(M.C[i])
        for s in range(o + 1, c):
            if has[s] and np.isfinite(r[s]) and s - 1 > o:
                rc.setdefault((s - o) // BUCKET, []).append(r[s])
        rpre += [r[s] for s in range(1, o) if has[s] and np.isfinite(r[s])]
        rpost += [r[s] for s in range(c + 1, e) if has[s] and np.isfinite(r[s])]
        for s in range(o + 1, c):
            if has[s] and M.N[i, s] > 0:
                k = (s - o) // BUCKET
                sz.setdefault(k, []).append(M.V[i, s] / M.N[i, s])
                rg.setdefault(k, []).append((M.H[i, s] - M.L[i, s]) / M.C[i, s])
    nb = max(rc.keys(), default=0) + 1
    med = lambda a: np.nanmedian(a, axis=0) if len(a) else np.full(S, np.nan)
    vol_cont = med(vc)
    floor = max(1.0, VOL_FLOOR_SHARE * float(np.nanmedian(vol_cont[1:390])) if np.any(np.isfinite(vol_cont[1:390])) else 1.0)
    return Profile(vol_cont=vol_cont, vol_pre=med(vp), vol_post=med(vq),
                   sig_cont=np.array([_robust_sigma(np.array(rc.get(k, []))) for k in range(nb)]),
                   sig_pre=_robust_sigma(np.array(rpre)), sig_post=_robust_sigma(np.array(rpost)),
                   size_cont=np.array([np.median(sz[k]) if k in sz else np.nan for k in range(nb)]),
                   range_cont=np.array([np.median(rg[k]) if k in rg else np.nan for k in range(nb)]),
                   vol_floor=floor, n_days=len(rows))


def _expected(prof: Profile, b: dict):
    """Volumen esperado, sigma, tamaño y rango por minuto (960) para un día concreto, alineados con sus tramos."""
    S = sessions.N_SLOTS
    o, c, e = b["open_slot"], b["close_slot"], b["end_slot"]
    ev = np.full(S, np.nan)
    ev[:o] = prof.vol_pre[:o]
    ev[o:c] = prof.vol_cont[:c - o]
    ev[c:e] = prof.vol_post[:e - c]
    ev = np.maximum(np.nan_to_num(ev), prof.vol_floor)
    sig = np.full(S, np.nan)
    sig[:o] = prof.sig_pre
    sig[c:e] = prof.sig_post
    for s in range(o, c):
        k = min((s - o) // BUCKET, len(prof.sig_cont) - 1)
        sig[s] = prof.sig_cont[k]
        if not np.isfinite(sig[s]):
            sig[s] = np.nanmedian(prof.sig_cont)
    sig = np.where(np.isfinite(sig), np.maximum(sig, SIGMA_FLOOR), np.nan)
    size = np.full(S, np.nan)
    rng = np.full(S, np.nan)
    for s in range(o, c):
        k = min((s - o) // BUCKET, len(prof.size_cont) - 1)
        size[s], rng[s] = prof.size_cont[k], prof.range_cont[k]
    return ev, sig, size, rng


# ── medidas de un día ──
def _m(value, *, series=None, k=1, fixed_slot=None, window=None, estimated=False, segment="continuous", note=None):
    v = float(value) if value is not None and np.isfinite(value) else np.nan
    return {"value": v, "series": series, "k": k, "fixed_slot": fixed_slot, "window": window,
            "estimated": estimated, "segment": segment, "note": note}


def _two(name, series, k, out, segment="continuous", estimated=False):
    up = np.where(series > 0, series, np.nan)
    dn = np.where(series < 0, -series, np.nan)
    out[f"{name}_up"] = _m(np.nanmax(up) if np.any(np.isfinite(up)) else np.nan, series=up, k=k, segment=segment,
                           estimated=estimated)
    out[f"{name}_dn"] = _m(np.nanmax(dn) if np.any(np.isfinite(dn)) else np.nan, series=dn, k=k, segment=segment,
                           estimated=estimated)


def _fixed_two(name, x, slot, window, out, segment, estimated=False):
    """Medida de instante fijo y dos lados: se normaliza la MAGNITUD |x| y el signo se guarda aparte.

    (Partirla en _up/_dn con 0 en el lado contrario llenaba la línea base de ceros e inflaba el z robusto.)"""
    out[name] = _m(abs(x) if np.isfinite(x) else np.nan, fixed_slot=slot, window=window, segment=segment,
                   estimated=estimated)
    out[name]["sign"] = int(np.sign(x)) if np.isfinite(x) else 0


def day_measures(M: DayMatrix, i: int, prof: Profile, prev_close: float, *, post: bool = True) -> dict:
    """Todas las medidas cat-v0 de una sesión. Devuelve {nombre: dict(value, series, ...)} y '_quality'."""
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return _day_measures(M, i, prof, prev_close, post=post)


def _day_measures(M: DayMatrix, i: int, prof: Profile, prev_close: float, *, post: bool = True) -> dict:
    b = M.meta[i]
    o, c, e = b["open_slot"], b["close_slot"], b["end_slot"]
    S = sessions.N_SLOTS
    ev, sig, size, rng = _expected(prof, b)
    Cf = _ffill(M.C[i])
    lc = np.log(Cf)
    has = ~np.isnan(M.C[i])
    V = np.nan_to_num(M.V[i])
    Nn = np.nan_to_num(M.N[i])
    out = {}
    cont = np.zeros(S, bool)
    cont[o + 1:c] = True                       # sin las barras mixtas de apertura y cierre

    # D1: desplazamiento en k minutos (en sigmas propias), D-up / D-dn
    z_by_k = {}
    for k in D1_WINDOWS:
        R = np.full(S, np.nan)
        R[k:] = lc[k:] - lc[:-k]
        valid = cont.copy()
        valid[: o + 1 + k] = False
        z = np.where(valid, R / (sig * np.sqrt(k)), np.nan)
        z_by_k[k] = z
        _two(f"D1_{k}", z, k, out)
    # D2: rango de una vela frente al típico
    d2 = np.where(cont & has, (M.H[i] - M.L[i]) / M.C[i] / rng, np.nan)
    out["D2_range"] = _m(np.nanmax(d2) if np.any(np.isfinite(d2)) else np.nan, series=d2)
    # D3: salto entre velas y hueco sin barras
    jump = np.full(S, np.nan)
    jump[1:] = np.abs(np.log(M.O[i][1:]) - lc[:-1]) / sig[1:]
    jump = np.where(cont & has & (np.arange(S) > o + 1), jump, np.nan)
    out["D3_jump"] = _m(np.nanmax(jump) if np.any(np.isfinite(jump)) else np.nan, series=jump)
    gap = np.where(cont, _runs(cont & ~has), np.nan)
    out["D3_gap"] = _m(np.nanmax(gap) if np.any(np.isfinite(gap)) else np.nan, series=gap,
                       note="minutos seguidos sin barra: sin operaciones o dato ausente (los trades lo distinguen)")
    # D4: distancia al VWAP acumulado de la negociación continua
    cv = np.cumsum(np.where(cont, np.nan_to_num(M.VW[i]) * V, 0.0))
    cvol = np.cumsum(np.where(cont, V, 0.0))
    vwap = np.where(cvol > 0, cv / np.where(cvol > 0, cvol, 1), np.nan)
    d4 = np.where(cont & (cvol > 0), lc - np.log(vwap), np.nan)
    _two("D4_vwap", d4, 1, out)
    # V1: volumen frente al perfil
    vr = {}
    for k in V1_WINDOWS:
        x = _rsum(np.where(cont, V, 0.0), k) / _rsum(np.where(cont, ev, 0.0), k)
        valid = cont.copy()
        valid[: o + k] = False
        vr[k] = np.where(valid, x, np.nan)
        out[f"V1_{k}"] = _m(np.nanmax(vr[k]) if np.any(np.isfinite(vr[k])) else np.nan, series=vr[k], k=k)
    # V2: tamaño medio por operación (15 min) frente al propio
    rv, rn = _rsum(np.where(cont, V, 0.0), 15), _rsum(np.where(cont, Nn, 0.0), 15)
    v2 = np.where(cont & (rn >= MIN_TRADES_SIZE), (rv / np.where(rn > 0, rn, 1)) / size, np.nan)
    v2[: o + 15] = np.nan
    out["V2_size_up"] = _m(np.nanmax(v2) if np.any(np.isfinite(v2)) else np.nan, series=v2, k=15)
    inv = np.where(np.isfinite(v2) & (v2 > 0), 1 / v2, np.nan)
    out["V2_size_dn"] = _m(np.nanmax(inv) if np.any(np.isfinite(inv)) else np.nan, series=inv, k=15)
    # I1 / I2 / I3 en ventanas de 15 min
    z15, v15 = z_by_k[15], vr[15]
    thin = np.where(np.isfinite(z15) & np.isfinite(v15) & (v15 <= THIN_VOL_RATIO), z15, np.nan)
    _two("I1_thin", thin, 15, out)
    stall = np.where(np.isfinite(z15) & np.isfinite(v15) & (np.abs(z15) <= STALL_Z), v15, np.nan)
    out["I2_stall"] = _m(np.nanmax(stall) if np.any(np.isfinite(stall)) else np.nan, series=stall, k=15)
    wv = _rsum(np.where(cont, np.nan_to_num(M.VW[i]) * V, 0.0), 15)
    wvol = _rsum(np.where(cont, V, 0.0), 15)
    i3 = np.where(cont & (wvol > 0) & (wv > 0), (lc - np.log(wv / np.where(wvol > 0, wvol, 1))) / (sig * np.sqrt(15)),
                  np.nan)
    i3[: o + 15] = np.nan
    _two("I3_vwap15", i3, 15, out)
    # P1: racha de minutos en la misma dirección
    r1 = np.full(S, np.nan)
    r1[1:] = lc[1:] - lc[:-1]
    sgn = np.where(cont & has & (np.arange(S) > o + 1) & np.isfinite(r1), np.sign(r1), 0)
    run_up, run_dn = _runs(sgn > 0), _runs(sgn < 0)
    out["P1_run_up"] = _m(np.max(run_up[cont]) if cont.any() else np.nan, series=np.where(cont, run_up, np.nan))
    out["P1_run_dn"] = _m(np.max(run_dn[cont]) if cont.any() else np.nan, series=np.where(cont, run_dn, np.nan))
    # P2: eficiencia direccional |Σr| / Σ|r|, con recorrido mínimo de una sigma de la ventana
    ra = np.where(cont & np.isfinite(r1) & (np.arange(S) > o + 1), r1, np.nan)
    for k in P2_WINDOWS:
        num, den = _rsum(ra, k), _rsum(np.abs(ra), k)
        nb = _rcount(cont & has, k)
        ok = cont & (nb >= 0.8 * k) & (den >= sig * np.sqrt(k))
        er = np.where(ok, num / np.where(den > 0, den, 1), np.nan)
        er[: o + 1 + k] = np.nan
        _two(f"P2_er{k}", er, k, out)
    # P3: minutos seguidos con volumen >= 2 veces el esperado
    hv = np.where(cont, _runs(cont & (V >= HIGH_VOL_MULT * ev)), np.nan)
    out["P3_highvol_run"] = _m(np.nanmax(hv) if np.any(np.isfinite(hv)) else np.nan, series=hv)

    # C1: últimos 5/10/30 min de la negociación continua (hasta la última barra continua, sin la mixta de cierre)
    last = c - 1
    for k in C1_WINDOWS:
        x = (lc[last] - lc[last - k]) / (sig[last] * np.sqrt(k)) if last - k > o else np.nan
        _fixed_two(f"C1_{k}", x, c, (last - k + 1, c), out, "continuous")
    # V3 / C2 (estimados con las barras mixtas)
    cont_vol = float(V[o + 1:c].sum())
    out["V3_close_est"] = _m(V[c] / cont_vol if cont_vol > 0 else np.nan, fixed_slot=c + 1, window=(c, c + 1),
                             estimated=True, segment="close_auction",
                             note="barra mixta de cierre (subasta + primer minuto de after hours) / volumen continuo")
    out["V3_open_est"] = _m(V[o] / cont_vol if cont_vol > 0 else np.nan, fixed_slot=o + 1, window=(o, o + 1),
                            estimated=True, segment="open_auction",
                            note="barra mixta de apertura (subasta + primer minuto continuo) / volumen continuo")
    # C5: hueco de apertura y primeros 5 minutos; PRE: premercado
    gap_ret = np.log(M.O[i][o]) - np.log(prev_close) if (has[o] and prev_close and prev_close > 0) else np.nan
    _fixed_two("C5_gap", gap_ret, o + 1, (o, o + 1), out, "open_auction")
    f5 = lc[o + 5] - lc[o] if has[o] else np.nan
    _fixed_two("C5_first5", f5 / (np.nanmedian(prof.sig_cont[:1]) * np.sqrt(5)) if np.isfinite(f5) else np.nan,
               o + 6, (o, o + 6), out, "continuous")
    pre_px = Cf[o - 1] if o > 0 else np.nan
    pre_ret = np.log(pre_px) - np.log(prev_close) if (np.isfinite(pre_px) and prev_close and prev_close > 0) else np.nan
    _fixed_two("PRE_ret", pre_ret, o, (0, o), out, "pre")
    pre_v = float(V[:o].sum())
    out["PRE_vol"] = _m(pre_v / float(np.sum(ev[:o])) if o > 0 else np.nan, fixed_slot=o, window=(0, o), segment="pre")

    # C3: after hours (solo en la pasada completa)
    if post and e > c + 1:
        ref = lc[last]
        for k in C3_WINDOWS:
            s = min(c + k, e - 1)
            x = lc[s] - ref if np.isfinite(lc[s]) else np.nan
            _fixed_two(f"C3_{k}", x, s + 1, (c, s + 1), out, "post")
        span = np.zeros(S, bool)
        span[c + 1:min(c + 1 + POST_EXT_MIN, e)] = True
        hi = np.where(span & has, np.log(M.H[i]) - ref, np.nan)
        lo = np.where(span & has, np.log(M.L[i]) - ref, np.nan)
        hi_run = np.fmax.accumulate(np.where(np.isfinite(hi), hi, -np.inf))
        lo_run = np.fmin.accumulate(np.where(np.isfinite(lo), lo, np.inf))
        up = np.where(span & np.isfinite(hi_run) & (hi_run > 0), hi_run, np.nan)
        dn = np.where(span & np.isfinite(lo_run) & (lo_run < 0), -lo_run, np.nan)
        out["C3_ext35_up"] = _m(np.nanmax(up) if np.any(np.isfinite(up)) else 0.0, series=up, segment="post")
        out["C3_ext35_dn"] = _m(np.nanmax(dn) if np.any(np.isfinite(dn)) else 0.0, series=dn, segment="post")
        out["C3_vol_est"] = _m(float(V[c + 1:c + 1 + POST_EXT_MIN].sum()) / float(np.sum(ev[c + 1:c + 1 + POST_EXT_MIN])),
                               fixed_slot=c + 1 + POST_EXT_MIN, window=(c + 1, c + 1 + POST_EXT_MIN), segment="post",
                               estimated=True, note="el volumen de las barras de after hours incluye comunicaciones "
                                                    "tardías a precio de referencia")
    n_cont = int(cont.sum())
    out["_quality"] = {"continuous_minutes": n_cont, "continuous_bar_coverage": round(float((cont & has).sum()) / n_cont, 4)
                       if n_cont else None, "longest_gap_minutes": float(np.nanmax(gap)) if np.any(np.isfinite(gap)) else 0,
                       "early_close": bool(b["early_close"]), "post_computed": bool(post),
                       "last_continuous_close": float(Cf[last]) if np.isfinite(Cf[last]) else None,
                       "first_bar_slot": int(np.argmax(has)) if has.any() else None}
    return out


def last_continuous_close(M: DayMatrix, i: int) -> float:
    b = M.meta[i]
    x = _ffill(M.C[i])[b["close_slot"] - 1]
    return float(x) if np.isfinite(x) else None


# ── normalización frente a la línea base ──
def normalize(x: float, base: np.ndarray, *, pct_hi: float = 99.0, z_hi: float = 4.0) -> dict:
    b = np.asarray(base, dtype=float)
    b = b[np.isfinite(b)]
    n = int(len(b))
    if not np.isfinite(x) or n == 0:
        return {"value": None if not np.isfinite(x) else float(x), "n": n, "pct": None, "z": None, "median": None,
                "mad_sigma": None, "threshold": None, "flag": False, "rule": None, "exceeds_baseline_max": None,
                "resolution_pct": round(100 / n, 2) if n else None}
    below, eq = int((b < x).sum()), int((b == x).sum())
    pct = 100.0 * (below + 0.5 * eq) / n
    med = float(np.median(b))
    mad = float(np.median(np.abs(b - med)) * 1.4826)
    z = (x - med) / mad if mad > 0 else None
    sb = np.sort(b)
    thr_pct = float(sb[min(n - 1, int(np.floor(pct_hi / 100 * n)))])
    thr_z = med + z_hi * mad if mad > 0 else np.inf
    by_pct, by_z = x > thr_pct, (z is not None and z >= z_hi)
    rule = "pct+z" if (by_pct and by_z) else ("pct" if by_pct else ("z" if by_z else None))
    return {"value": float(x), "n": n, "pct": round(pct, 2), "z": round(float(z), 2) if z is not None else None,
            "median": med, "mad_sigma": mad, "threshold": float(min(thr_pct, thr_z)),
            "threshold_pct": thr_pct, "threshold_z": float(thr_z) if np.isfinite(thr_z) else None,
            "flag": bool(by_pct or by_z), "rule": rule, "exceeds_baseline_max": bool(x > sb[-1]),
            "resolution_pct": round(100 / n, 2)}


def crossings(series: np.ndarray, thr: float, k: int, max_runs: int = 5) -> list:
    """Tramos contiguos de la serie por encima del umbral: (primer minuto que lo supera, pico, último)."""
    if series is None or thr is None or not np.isfinite(thr):
        return []
    above = np.isfinite(series) & (series > thr) if thr >= 0 else np.isfinite(series) & (series >= thr)
    out, s, n = [], 0, len(series)
    while s < n and len(out) < max_runs:
        if above[s]:
            e = s
            while e + 1 < n and above[e + 1]:
                e += 1
            seg = series[s:e + 1]
            out.append({"first": s, "peak": int(s + np.nanargmax(seg)), "last": e, "k": k})
            s = e + 1
        else:
            s += 1
    return out
