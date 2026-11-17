"""G1.5 — descarga acotada de un episodio (trades del día por ventanas + quotes de los tramos pedidos).

Uso: py -3 g15_fetch_episode.py SYMBOL YYYY-MM-DD [HH:MM-HH:MM ...]
Imprime la estimación antes de descargar y registra el coste real en results/g15_fetch_log.jsonl.
"""
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from micro import episode, runtime, storage  # noqa: E402

if __name__ == "__main__":
    sym, day, *qr = sys.argv[1:]
    p = runtime.alpaca()
    est = episode.estimate(p, sym, day, qr)
    print(json.dumps(est), flush=True)
    t0 = time.time()
    res = episode.fetch_day(p, sym, day, quote_ranges=qr)
    rec = {"symbol": sym, "day": day, "quote_ranges": qr, "estimate": est, "wall_s": round(time.time() - t0, 1),
           "units": res, "sizes": episode.sizes(sym, day)}
    with open(storage.root() / "results" / "g15_fetch_log.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, default=str) + "\n")
    print(json.dumps(rec["sizes"]), rec["wall_s"], flush=True)
