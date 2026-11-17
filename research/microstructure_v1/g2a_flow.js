// G2A — Flow Score y Early Flow con el código exacto de la pestaña (shared/flow-score.js).
// Entrada: MICRO_DATA_DIR/features/flow_in.csv (g2a_flow.py). Salida: flow_out.csv (entity,date,flow,ef).
const fs = require("fs"), readline = require("readline"), path = require("path");
const { computeFlowScore, computeEarlyFlowScore } = require(path.join(__dirname, "..", "..", "shared", "flow-score.js"));
const dir = process.argv[2];
const num = s => (s === "" ? null : Number(s));
const str = s => (s === "" ? null : s);
const bool = s => (s === "" ? null : s === "1");
(async () => {
  const rl = readline.createInterface({ input: fs.createReadStream(path.join(dir, "flow_in.csv")) });
  const out = fs.createWriteStream(path.join(dir, "flow_out.csv"));
  out.write("entity,date,flow,ef\n");
  let header = true, n = 0;
  for await (const line of rl) {
    if (header) { header = false; continue; }
    const [e, date, kd, pkd, k3, pk3, kw, atr, patr, fh, rsi, w1, m1, mb] = line.split(",");
    const d = { konc_d_state: str(kd), konc_3d_state: str(k3), konc_w_state: str(kw), atrPct: num(atr),
                fromHigh: num(fh), rsi: num(rsi), w1: num(w1), m1: num(m1), macdBull: bool(mb) };
    const prev = { konc_d_state: str(pkd), konc_3d_state: str(pk3), atrPct: num(patr) };
    out.write(`${e},${date},${computeFlowScore(d)},${computeEarlyFlowScore(d, prev)}\n`);
    n++;
  }
  out.end();
  console.log("filas", n);
})();
