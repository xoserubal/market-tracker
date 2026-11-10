// Early Flow Score con el código exacto de la pestaña (shared/flow-score.js).
// Entrada: _work/earlyflow_in.csv (build_features.py). Salida: _work/earlyflow_out.csv
const fs = require("fs"), readline = require("readline"), path = require("path");
const { computeEarlyFlowScore } = require(path.join(__dirname, "..", "..", "shared", "flow-score.js"));
const num = s => (s === "" ? null : Number(s));
const str = s => (s === "" ? null : s);
(async () => {
  const rl = readline.createInterface({ input: fs.createReadStream(path.join(__dirname, "_work", "earlyflow_in.csv")) });
  const out = fs.createWriteStream(path.join(__dirname, "_work", "earlyflow_out.csv"));
  out.write("ticker,date,ef\n");
  let header = true, n = 0;
  for await (const line of rl) {
    if (header) { header = false; continue; }
    const [t, date, kd, pkd, k3, pk3, kw, atr, patr, fh, rsi, w1, m1] = line.split(",");
    const d = { konc_d_state: str(kd), konc_3d_state: str(k3), konc_w_state: str(kw), atrPct: num(atr),
                fromHigh: num(fh), rsi: num(rsi), w1: num(w1), m1: num(m1) };
    const prev = { konc_d_state: str(pkd), konc_3d_state: str(pk3), atrPct: num(patr) };
    out.write(`${t},${date},${computeEarlyFlowScore(d, prev)}\n`);
    n++;
  }
  out.end();
  console.log("filas", n);
})();
