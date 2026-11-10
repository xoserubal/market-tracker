// Clasificación Leader/Improving/... de cada ETF sectorial frente a SPY, día a día, con shared/relative-lib.js.
// Entrada: _work/sector_in.json. Salida: _work/sector_out.json  {etf: {fecha: etiqueta}}
const fs = require("fs"), path = require("path");
const { buildRowFromRatio, classify } = require(path.join(__dirname, "..", "..", "shared", "relative-lib.js"));
const input = JSON.parse(fs.readFileSync(path.join(__dirname, "_work", "sector_in.json"), "utf8"));
const out = {};
for (const [etf, ratio] of Object.entries(input)) {
  out[etf] = {};
  for (let i = 0; i < ratio.length; i++) {
    out[etf][ratio[i].date] = classify(buildRowFromRatio({ a: etf, b: "SPY" }, ratio.slice(0, i + 1))).label;
  }
}
fs.writeFileSync(path.join(__dirname, "_work", "sector_out.json"), JSON.stringify(out));
console.log(Object.fromEntries(Object.entries(out).map(([k, v]) => [k, Object.keys(v).length])));
