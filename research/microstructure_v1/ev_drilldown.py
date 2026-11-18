"""Desglose bajo demanda con trades (y quotes si aportan) + ficha del caso (E1).

    py -3 ev_drilldown.py --day 2026-11-17 --episode <episode_id> [--quotes auto|yes|no] [--no-download]
    py -3 ev_drilldown.py --day 2026-11-17 --symbol PLTR --window 15:30-17:00        # cualquier valor/fecha/ventana
    py -3 ev_drilldown.py --day 2026-11-17 --list                                      # episodios del día

Salidas: MICRO_DATA_DIR/events/drilldowns/<clave>.json (privado) y fichas/<SYMBOL>_<DÍA>_<clave>.md (solo agregados).
Actualiza el estado de las alertas desglosadas en el registro. El periodo reservado de G2A está bloqueado salvo
--allow-test-period (queda anotado en el registro de exposiciones).
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from micro import calendar, drilldown, event_catalog as cat, event_store, runtime, sessions  # noqa: E402

FICHAS = HERE / "fichas"
MAX_WINDOW_MIN = 150


def _ny(ts, fmt="%H:%M"):
    return pd.Timestamp(ts).tz_convert(sessions.NY).strftime(fmt) if ts is not None and str(ts) not in ("", "None", "NaT") else "—"


def _f(x, nd=2, pct=False):
    if x is None or (isinstance(x, float) and pd.isna(x)):
        return "—"
    return f"{x * 100:.{nd}f} %" if pct else f"{x:,.{nd}f}".replace(",", " ")


def episode_window(day, ep, alerts, focus="auto"):
    """Ventana del desglose. Si el episodio dura más de MAX_WINDOW_MIN se elige un foco: 'open' (subasta de apertura y
    primera hora), 'close' (cierre y after hours), 'peak' (alerta de mayor |z|) o 'auto' (cierre si hay alertas de
    cierre o after hours; si no, la alerta principal). El resto de alertas se listan como fuera de ventana."""
    st, en = pd.Timestamp(ep["t_start_utc"]), pd.Timestamp(ep["t_end_utc"])
    b = sessions.bounds(day)
    if focus == "open":
        return drilldown.plan_window(day, b["open"] - pd.Timedelta(minutes=5), b["open"] + pd.Timedelta(minutes=60)),             "foco en la apertura"
    if focus == "auto" and (en - st).total_seconds() / 60 <= MAX_WINDOW_MIN:
        return drilldown.plan_window(day, st, en), "episodio completo"
    a = max(alerts, key=lambda a: abs(a["z"]) if a.get("z") is not None and not pd.isna(a["z"]) else 0)
    late = [x for x in alerts if x["segment"] in ("post", "close_auction")]
    if focus == "close" or (focus == "auto" and late):
        b = sessions.bounds(day)
        return drilldown.plan_window(day, b["close"] - pd.Timedelta(minutes=20), b["close"] + pd.Timedelta(minutes=40)), \
            "episodio largo: ventana del cierre y after hours"
    return drilldown.plan_window(day, a["t_start_utc"], a["t_end_utc"]), f"episodio largo: ventana de la alerta {a['measure']}"


def render(dd: dict, ep: dict, alerts: list, sd: dict, why: str) -> str:
    sym, day = dd["symbol"], dd["day"]
    S = dd["segments"]["segments"]
    den = dd["segments"]["denominators"]
    P = dd["segments"]["prices"]
    L = []
    L.append(f"# Ficha — {sym}, {day} ({dd['window_ny']} NY)\n")
    L.append(f"Generada por `ev_drilldown.py` · catálogo {dd['catalog_version']} · detector {dd['detector_version']} · "
             f"código {dd['code_version']}. **Descriptiva:** no interpreta intención ni predice nada.\n")
    if ep:
        L.append(f"Episodio `{ep['episode_id']}`: {len(alerts)} alerta(s), códigos {', '.join(json.loads(ep['codes']) if isinstance(ep['codes'], str) else ep['codes'])}, "
                 f"de {_ny(ep['t_start_utc'])} a {_ny(ep['t_end_utc'])} NY. Ventana del desglose: {why}.\n")
    L.append(f"Laboratorio: {ep.get('lab_url') if ep else 'http://127.0.0.1:8765/?symbol=' + sym + '&day=' + day}\n")
    if sd:
        L.append(f"Línea base: {sd.get('baseline_n')} sesiones ({'CORTA: resultados indeterminados' if sd.get('baseline_short') else 'suficiente'}); "
                 f"{sd.get('baseline_rule')}. Cierre anticipado: {'sí' if sd.get('early_close') else 'no'}. "
                 f"Sector: {sd.get('sector') or '—'} ({sd.get('sector_etf') or '—'}).\n")
    if alerts:
        L.append("## Alertas (barras de 1 minuto, frente a la propia historia)\n")
        L.append("| Código | Medida | Tramo | Inicio | Detectable | Fin | Valor | Percentil | z robusto | n | Estado tras el desglose |")
        L.append("|---|---|---|---|---|---|---:|---:|---:|---:|---|")
        st = dd.get("statuses", {})
        for a in sorted(alerts, key=lambda a: a["t_detectable_utc"]):
            s, w = st.get(a["event_id"], (a["status"], a.get("status_note") or ""))
            inside = pd.Timestamp(a["t_end_utc"]) > pd.Timestamp(dd["window_utc"][0]) and \
                pd.Timestamp(a["t_start_utc"]) < pd.Timestamp(dd["window_utc"][1])
            L.append(f"| {a['code']} | `{a['measure']}`{' (−)' if a.get('direction') == -1 else ''} | "
                     f"{sessions.SEGMENT_LABELS.get(a['segment'], a['segment'])} | {_ny(a['t_start_utc'])} | "
                     f"{_ny(a['t_detectable_utc'])} | {_ny(a['t_end_utc'])} | {_f(a['peak_value'], 4)} | "
                     f"{_f(a['pct'], 1)} | {_f(a['z'], 2)} | {a['n']} | "
                     f"{cat.STATUSES.get(s, s) if inside else 'fuera de la ventana del desglose'}{(' — ' + w) if w and inside else ''} |")
        L.append("\nCon una línea base de n sesiones, la resolución del percentil es 100/n puntos; el percentil 99 "
                 "equivale a superar el máximo de la base. Los umbrales son referencias iniciales, sin calibrar.\n")
    L.append("## Tramos exactos (trades de la ventana)\n")
    L.append("| Tramo | Acciones | Impresiones | Primero | Último | Máx. | Mín. | % impresiones odd lot | % acciones TRF |")
    L.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    for k, v in S.items():
        if v["prints"] == 0:
            continue
        L.append(f"| {sessions.SEGMENT_LABELS.get(k, k)} | {_f(v['shares'], 0)} | {_f(v['prints'], 0)} | {_f(v['first'])} | "
                 f"{_f(v['last'])} | {_f(v['high'])} | {_f(v['low'])} | {_f(v['odd_lot_print_share'], 1, True)} | "
                 f"{_f(v['trf_share_of_shares'], 1, True)} |")
    L.append(f"\nDenominadores (solo la ventana): continua {_f(den['continuous'], 0)} · regular con subastas "
             f"{_f(den['regular_with_auctions'], 0)} · total de la ventana {_f(den['day_total'], 0)} acciones. "
             "Las impresiones oficiales (M, Q) no suman volumen.\n")
    sh = dd["segments"]["shares_of"]["close_auction"]
    if S["close_auction"]["prints"]:
        L.append(f"Subasta de cierre: {_f(S['close_auction']['shares'], 0)} acciones a {_f(P['close_auction_price'])}; "
                 f"cierre oficial {_f(P['official_close'])} ({P['official_close_source']}); última continua "
                 f"{_f(P['last_continuous'])} ({P.get('close_vs_last_continuous_bps', '—')} pb).\n")
        ds = dd.get("day_shares") or {}
        if ds.get("computed"):
            c = ds["close_auction"]
            L.append(f"**Cuota exacta de la subasta de cierre sobre la sesión regular** (trades de toda la sesión): "
                     f"{_f(c['vs_continuous'], 1, True)} del volumen continuo · {_f(c['vs_regular_with_auctions'], 1, True)} "
                     f"de la sesión regular con subastas. Denominadores: continua {_f(ds['denominators']['continuous'], 0)}, "
                     f"regular con subastas {_f(ds['denominators']['regular_with_auctions'], 0)} acciones.\n")
        elif ds:
            ap = dd.get("close_auction_vs_bar_continuous") or {}
            L.append(f"Cuota exacta sobre el día: no calculada ({ds.get('reason')}). Aproximación: "
                     f"{_f(ap.get('share'), 1, True)} = subasta exacta / volumen continuo de las barras del día "
                     f"({_f(ap.get('continuous_volume_bars'), 0)} acciones; {ap.get('note', '')}).\n")
    be = dd.get("bar_estimates") or {}
    if be and (be["volume_by_bar_segment"]["close_mixed"] or S["close_auction"]["prints"]):
        v = be["volume_by_bar_segment"]
        L.append(f"Con barras, la barra mixta de cierre sumaba {_f(v['close_mixed'], 0)} acciones (subasta + primer minuto "
                 f"de after hours) frente a {_f(S['close_auction']['shares'], 0)} de subasta real. Nota: {be['note']}.\n")
    ms = dd.get("minute_status") or {}
    if ms:
        L.append(f"Minutos de negociación continua sin barra en la ventana: {ms.get('continuous_without_bar', '—')} "
                 f"(sin operaciones {ms.get('no_trade', '—')}, dato ausente {ms.get('missing_data', '—')}, "
                 f"con operaciones pero sin barra {ms.get('bar_missing_but_traded', '—')}).\n")
    pr = dd.get("profile") or {}
    if pr:
        va = pr.get("value_area", {})
        L.append("## Perfil de volumen de la ventana (continua, premercado y after hours)\n")
        L.append(f"POC {_f(va.get('poc'))} · área de valor 70 %: {_f(va.get('val'))}–{_f(va.get('vah'))} · "
                 f"{pr['levels']} niveles de {pr['step']} $ · nivel más negociado {_f(pr['top_level_share'], 1, True)} "
                 f"del volumen (±1 nivel: {_f(pr['poc_pm1_share'], 1, True)}). Sin línea base de trades: no se puede "
                 "decir si esa concentración es habitual en este valor (N1 queda descriptiva).\n")
    lr = dd["late_reports"]
    L.append(f"Comunicaciones tardías o a precio de referencia en la ventana (C4): {_f(lr['shares'], 0)} acciones en "
             f"{lr['prints']} impresiones; la mayor, {_f(lr['largest'], 0)}.\n")
    L.append("## Operaciones más grandes de la ventana (N3, descriptivo)\n")
    L.append("| Hora NY | Precio | Acciones | Mercado | Condiciones | Tramo |")
    L.append("|---|---:|---:|---|---|---|")
    for r in dd["largest_prints"][:6]:
        L.append(f"| {r['ny']} | {_f(r['price'])} | {_f(r['size'], 0)} | {r['exchange']} | `{r['conditions']}` | "
                 f"{sessions.SEGMENT_LABELS.get(r['segment'], r['segment'])} |")
    ag = dd.get("aggressor")
    if ag and ag.get("window"):
        L.append("\n## Clasificadores de agresor (con quotes; estimación)\n")
        L.append("| Tramo | Acciones | Tick | Lee-Ready | EMO | Bid-ask estricto | Diferencial mediano | Signos |")
        L.append("|---|---:|---:|---:|---:|---:|---:|---|")
        rows = [("ventana con quotes", ag["window"])] + [(f"alerta {x['measure']}", x) for x in ag["by_alert"]]
        for name, w in rows:
            cell = lambda m: f"{w[m]['delta_pct_of_volume']:+.1f} % (indet. {w[m]['undetermined_pct']:.0f} %)"
            L.append(f"| {name} | {_f(w['shares'], 0)} | {cell('tick')} | {cell('lr')} | {cell('emo')} | {cell('bidask')} | "
                     f"{_f(w['spread_bps_median'])} pb | {w['sign_agreement']} |")
        L.append(f"\n{ag['caveat']}. Sin quotes de sesiones anteriores, el delta no está normalizado.\n")
    rc = [r for r in dd["rechecks"] if r.get("checked")]
    if rc:
        L.append("## Comprobación de las alertas de precio con trades\n")
        for r in rc:
            L.append(f"- `{r['measure']}`: {r['trade_return_pct']:+.3f} % con trades ({_f(r['price_start'])} → "
                     f"{_f(r['price_end'])}) → {cat.STATUSES.get(r['new_status'], r['new_status'])}{(' — ' + r['why']) if r['why'] else ''}")
    L.append("\n## Procedencia\n")
    L.append(f"Trades cargados: {dd['trades_loaded']:,} (operaciones repetidas con el mismo identificador eliminadas: "
             f"{dd.get('duplicate_ids_removed', 0)}) · quotes: {dd['quotes_loaded']:,}. Descarga de este desglose: "
             f"{dd['fetch'].get('requests', 0)} peticiones. Unidades: {len(dd['data_units'])} (claves y sha256 en el JSON "
             "privado del desglose).".replace(",", " "))
    return "\n".join(L) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--day", required=True)
    ap.add_argument("--episode")
    ap.add_argument("--symbol")
    ap.add_argument("--window", help="HH:MM-HH:MM en hora de Nueva York")
    ap.add_argument("--quotes", choices=["auto", "yes", "no"], default="auto")
    ap.add_argument("--no-download", action="store_true")
    ap.add_argument("--allow-test-period", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--focus", choices=["auto", "open", "close", "peak"], default="auto")
    a = ap.parse_args()
    eps = event_store.read("episodes", a.day)
    if a.list:
        print(eps[["episode_id", "symbol", "codes", "n_alerts", "t_start_utc", "t_end_utc", "status"]].to_string()
              if len(eps) else "sin episodios")
        return
    prov = None if a.no_download else runtime.alpaca()
    alerts, ep, sd, why = [], None, None, "ventana manual"
    if a.episode:
        ep = eps[eps["episode_id"] == a.episode].iloc[0].to_dict()
        al = event_store.read("alerts", a.day)
        alerts = al[al["episode_id"] == a.episode].to_dict("records")
        sym = ep["symbol"]
        win, why = episode_window(a.day, ep, alerts, a.focus)
        key = a.episode
    else:
        sym = a.symbol.upper()
        s, e = a.window.split("-")
        win = calendar.ny_range(a.day, s, e)
        key = f"manual_{sym}_{a.day}_{s.replace(':', '')}{e.replace(':', '')}"
        al = event_store.read("alerts", a.day)
        if len(al):
            al = al[(al["symbol"] == sym)]
            alerts = [x for x in al.to_dict("records") if pd.Timestamp(x["t_end_utc"]) > win[0]
                      and pd.Timestamp(x["t_start_utc"]) < win[1]]
    sdt = event_store.read("symbol_days", a.day)
    if len(sdt):
        r = sdt[sdt["symbol"] == sym]
        if len(r):
            sd = r.iloc[-1].to_dict()
    dd = drilldown.run(sym, a.day, win, alerts=alerts, provider=prov, quotes=a.quotes, key=key,
                       allow_test_period=a.allow_test_period)
    if dd.get("error"):
        raise SystemExit(dd["error"])
    event_store.drilldown_path(key).write_text(json.dumps(dd, indent=1, default=str), encoding="utf-8")
    drilldown.apply_statuses(a.day, dd["statuses"])
    FICHAS.mkdir(exist_ok=True)
    out = FICHAS / f"{sym}_{a.day}_{key[:24]}.md"
    out.write_text(render(dd, ep, alerts, sd, why), encoding="utf-8")
    print(json.dumps({"ficha": str(out), "statuses": dd["statuses"], "fetch": dd["fetch"],
                      "seconds": dd["seconds"]}, indent=1, default=str))


if __name__ == "__main__":
    main()
