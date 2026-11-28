'use strict';
// COPIA CONGELADA del cálculo de Cycle (cycle.html) para el registro semanal de giros sectoriales.
// Generada el 2026-11-28 por make_cycle_copy.js desde cycle.html (huella de fragmentos 57bf3c57271f7b3b11d461c7c0e66fc10f8eae44c95d9df23c2ee9cc243c4492).
// No editar a mano. Si cycle.html cambia, el registro se detiene (registry.js) hasta verificar de nuevo la
// equivalencia (test_cycle_equivalence.js) y regenerar esta copia con autorización.
// Tabla: solo los campos que usa el cálculo (fase, orden, categoría, tickers y su papel).

const ORIGINAL_SHA256 = "57bf3c57271f7b3b11d461c7c0e66fc10f8eae44c95d9df23c2ee9cc243c4492";
const COPY_VERSION = 'cycle-copy-1';

const CYCLE_MAP = [
 {
  "phase": "Early Bull",
  "short": "Early Bull",
  "order": 1,
  "category": "Transportation",
  "sectors": [
   {
    "name": "Railroads",
    "tickers": [
     {
      "ticker": "IYT",
      "role": "proxy",
      "name": "iShares US Transportation"
     },
     {
      "ticker": "UNP",
      "role": "leader",
      "name": "Union Pacific"
     },
     {
      "ticker": "CSX",
      "role": "leader",
      "name": "CSX Corp"
     },
     {
      "ticker": "NSC",
      "role": "subsegment",
      "name": "Norfolk Southern"
     }
    ]
   },
   {
    "name": "Shipping",
    "tickers": [
     {
      "ticker": "ZIM",
      "role": "high_beta",
      "name": "ZIM Integrated Shipping"
     },
     {
      "ticker": "MATX",
      "role": "subsegment",
      "name": "Matson Inc"
     }
    ]
   },
   {
    "name": "Trucking & Logistics",
    "tickers": [
     {
      "ticker": "ODFL",
      "role": "subsegment",
      "name": "Old Dominion Freight"
     },
     {
      "ticker": "FDX",
      "role": "subsegment",
      "name": "FedEx"
     }
    ]
   }
  ]
 },
 {
  "phase": "Early → Mid Bull",
  "short": "E→M Bull",
  "order": 2,
  "category": "Technology",
  "sectors": [
   {
    "name": "Semiconductors",
    "tickers": [
     {
      "ticker": "NVDA",
      "role": "high_beta",
      "name": "NVIDIA"
     },
     {
      "ticker": "AVGO",
      "role": "leader",
      "name": "Broadcom"
     },
     {
      "ticker": "ASML",
      "role": "leader",
      "name": "ASML Holding"
     },
     {
      "ticker": "SMH",
      "role": "proxy",
      "name": "VanEck Semiconductors"
     }
    ]
   },
   {
    "name": "Computers & Electronics",
    "tickers": [
     {
      "ticker": "MSFT",
      "role": "leader",
      "name": "Microsoft"
     },
     {
      "ticker": "AAPL",
      "role": "leader",
      "name": "Apple"
     },
     {
      "ticker": "GOOGL",
      "role": "leader",
      "name": "Alphabet"
     },
     {
      "ticker": "XLK",
      "role": "proxy",
      "name": "Technology Select SPDR"
     }
    ]
   }
  ]
 },
 {
  "phase": "Mid → Late Bull",
  "short": "M→L Bull",
  "order": 3,
  "category": "Capital Goods",
  "sectors": [
   {
    "name": "Industrials & Electrical",
    "tickers": [
     {
      "ticker": "XLI",
      "role": "proxy",
      "name": "Industrials Select SPDR"
     },
     {
      "ticker": "CAT",
      "role": "leader",
      "name": "Caterpillar"
     },
     {
      "ticker": "ETN",
      "role": "leader",
      "name": "Eaton Corp"
     },
     {
      "ticker": "DE",
      "role": "leader",
      "name": "Deere & Company"
     },
     {
      "ticker": "ITW",
      "role": "subsegment",
      "name": "Illinois Tool Works"
     }
    ]
   },
   {
    "name": "Machinery, Trucks & Pollution Ctrl",
    "tickers": [
     {
      "ticker": "PCAR",
      "role": "subsegment",
      "name": "PACCAR Inc"
     },
     {
      "ticker": "PH",
      "role": "subsegment",
      "name": "Parker Hannifin"
     },
     {
      "ticker": "XYL",
      "role": "subsegment",
      "name": "Xylem"
     }
    ]
   }
  ]
 },
 {
  "phase": "Late Bull",
  "short": "Late Bull",
  "order": 4,
  "category": "Basic Industries & Materials",
  "sectors": [
   {
    "name": "Metals & Mining",
    "tickers": [
     {
      "ticker": "FCX",
      "role": "proxy",
      "name": "Freeport-McMoRan"
     },
     {
      "ticker": "BHP",
      "role": "leader",
      "name": "BHP Group"
     },
     {
      "ticker": "RIO",
      "role": "leader",
      "name": "Rio Tinto"
     },
     {
      "ticker": "NUE",
      "role": "subsegment",
      "name": "Nucor Corp"
     },
     {
      "ticker": "LIN",
      "role": "subsegment",
      "name": "Linde"
     }
    ]
   },
   {
    "name": "Chemicals, Containers & Paper",
    "tickers": [
     {
      "ticker": "XLB",
      "role": "proxy",
      "name": "Materials Select SPDR"
     },
     {
      "ticker": "LYB",
      "role": "subsegment",
      "name": "LyondellBasell"
     },
     {
      "ticker": "IP",
      "role": "subsegment",
      "name": "International Paper"
     }
    ]
   }
  ]
 },
 {
  "phase": "Late Bull → Top — Oil & Gas",
  "short": "Oil & Gas",
  "order": 5,
  "category": "Oil & Gas",
  "sectors": [
   {
    "name": "🛢 Oil & Gas",
    "tickers": [
     {
      "ticker": "XOM",
      "role": "leader",
      "name": "Exxon Mobil"
     },
     {
      "ticker": "CVX",
      "role": "leader",
      "name": "Chevron"
     },
     {
      "ticker": "COP",
      "role": "subsegment",
      "name": "ConocoPhillips"
     },
     {
      "ticker": "EOG",
      "role": "subsegment",
      "name": "EOG Resources"
     },
     {
      "ticker": "DVN",
      "role": "subsegment",
      "name": "Devon Energy"
     },
     {
      "ticker": "FANG",
      "role": "high_beta",
      "name": "Diamondback Energy"
     },
     {
      "ticker": "SLB",
      "role": "high_beta",
      "name": "Schlumberger (SLB)"
     },
     {
      "ticker": "XLE",
      "role": "proxy",
      "name": "Energy Select SPDR"
     }
    ]
   }
  ]
 },
 {
  "phase": "Late Bull → Top — Uranium",
  "short": "Uranium",
  "order": 6,
  "category": "Uranium",
  "sectors": [
   {
    "name": "☢ Uranium",
    "tickers": [
     {
      "ticker": "URNM",
      "role": "proxy",
      "name": "Sprott Uranium Miners (URNM)"
     },
     {
      "ticker": "URA",
      "role": "proxy",
      "name": "Global X Uranium (URA)"
     },
     {
      "ticker": "CCJ",
      "role": "leader",
      "name": "Cameco"
     },
     {
      "ticker": "NXE",
      "role": "high_beta",
      "name": "NexGen Energy"
     },
     {
      "ticker": "DNN",
      "role": "high_beta",
      "name": "Denison Mines"
     },
     {
      "ticker": "LEU",
      "role": "subsegment",
      "name": "Centrus Energy"
     },
     {
      "ticker": "UEC",
      "role": "subsegment",
      "name": "Uranium Energy Corp"
     },
     {
      "ticker": "BWXT",
      "role": "subsegment",
      "name": "BWX Technologies"
     }
    ]
   }
  ]
 },
 {
  "phase": "Late Bull → Top — Coal & Steel Inputs",
  "short": "Coal & Steel",
  "order": 7,
  "category": "Coal & Steel Inputs",
  "sectors": [
   {
    "name": "🪨 Coal & Steel Inputs",
    "tickers": [
     {
      "ticker": "HCC",
      "role": "leader",
      "name": "Warrior Met Coal"
     },
     {
      "ticker": "AMR",
      "role": "leader",
      "name": "Alpha Metallurgical Resources"
     },
     {
      "ticker": "BTU",
      "role": "subsegment",
      "name": "Peabody Energy"
     },
     {
      "ticker": "CNR",
      "role": "subsegment",
      "name": "Core Natural Resources"
     },
     {
      "ticker": "CLF",
      "role": "subsegment",
      "name": "Cleveland-Cliffs"
     },
     {
      "ticker": "TECK",
      "role": "proxy",
      "name": "Teck Resources"
     }
    ]
   }
  ]
 },
 {
  "phase": "Early Bear",
  "short": "Early Bear",
  "order": 8,
  "category": "Staples & Healthcare",
  "sectors": [
   {
    "name": "Consumer Staples & Defensive",
    "tickers": [
     {
      "ticker": "XLP",
      "role": "proxy",
      "name": "Consumer Staples SPDR"
     },
     {
      "ticker": "WMT",
      "role": "defensive",
      "name": "Walmart"
     },
     {
      "ticker": "PG",
      "role": "defensive",
      "name": "Procter & Gamble"
     },
     {
      "ticker": "KO",
      "role": "defensive",
      "name": "Coca-Cola"
     },
     {
      "ticker": "MO",
      "role": "defensive",
      "name": "Altria"
     }
    ]
   },
   {
    "name": "Healthcare & Pharma",
    "tickers": [
     {
      "ticker": "XLV",
      "role": "proxy",
      "name": "Healthcare Select SPDR"
     },
     {
      "ticker": "JNJ",
      "role": "leader",
      "name": "Johnson & Johnson"
     },
     {
      "ticker": "LLY",
      "role": "high_beta",
      "name": "Eli Lilly"
     }
    ]
   }
  ]
 },
 {
  "phase": "Late Bear (Approx.)",
  "short": "L.Bear Appr.",
  "order": 9,
  "category": "Utilities",
  "sectors": [
   {
    "name": "Electric, Gas & Telecom Infra",
    "tickers": [
     {
      "ticker": "XLU",
      "role": "proxy",
      "name": "Utilities Select SPDR"
     },
     {
      "ticker": "NEE",
      "role": "leader",
      "name": "NextEra Energy"
     },
     {
      "ticker": "DUK",
      "role": "leader",
      "name": "Duke Energy"
     },
     {
      "ticker": "SO",
      "role": "leader",
      "name": "Southern Company"
     },
     {
      "ticker": "AEP",
      "role": "leader",
      "name": "American Electric Power"
     },
     {
      "ticker": "D",
      "role": "subsegment",
      "name": "Dominion Energy"
     },
     {
      "ticker": "XEL",
      "role": "subsegment",
      "name": "Xcel Energy"
     },
     {
      "ticker": "AMT",
      "role": "subsegment",
      "name": "American Tower"
     }
    ]
   }
  ]
 },
 {
  "phase": "Late Bear",
  "short": "Late Bear",
  "order": 10,
  "category": "Financials & Cyclicals",
  "sectors": [
   {
    "name": "Banking & Finance",
    "tickers": [
     {
      "ticker": "JPM",
      "role": "leader",
      "name": "JPMorgan Chase"
     },
     {
      "ticker": "BAC",
      "role": "leader",
      "name": "Bank of America"
     },
     {
      "ticker": "GS",
      "role": "subsegment",
      "name": "Goldman Sachs"
     },
     {
      "ticker": "SCHW",
      "role": "subsegment",
      "name": "Charles Schwab"
     },
     {
      "ticker": "KKR",
      "role": "high_beta",
      "name": "KKR & Co"
     },
     {
      "ticker": "XLF",
      "role": "proxy",
      "name": "Financials Select SPDR"
     }
    ]
   },
   {
    "name": "Consumer Cyclical (Recovery)",
    "tickers": [
     {
      "ticker": "AMZN",
      "role": "leader",
      "name": "Amazon"
     },
     {
      "ticker": "TSLA",
      "role": "high_beta",
      "name": "Tesla"
     },
     {
      "ticker": "XHB",
      "role": "proxy",
      "name": "Homebuilders ETF"
     },
     {
      "ticker": "DHI",
      "role": "subsegment",
      "name": "DR Horton"
     }
    ]
   }
  ]
 }
];

function accelInfo(pp) {
  if (pp == null || isNaN(pp)) return { pp: null, symbol: '—' };
  if (pp > 2)  return { pp, symbol: '▲▲' };
  if (pp > 0)  return { pp, symbol: '▲' };
  if (pp > -2) return { pp, symbol: '▽' };
  return { pp, symbol: '▽▽' };
}
function stdev(arr) {
  if (!arr.length) return null;
  const mean = arr.reduce((a, b) => a + b, 0) / arr.length;
  const variance = arr.reduce((a, b) => a + (b - mean) ** 2, 0) / arr.length;
  return Math.sqrt(variance);
}
function calcPhaseScores(list, rows) {
  const spy = rows['SPY'];
  const spyM3 = spy?.m3 ?? null, spyM1 = spy?.m1 ?? null;

  return list.map(phase => {
    const allT = phase.sectors.flatMap(s => s.tickers);
    const dataCount = allT.filter(t => rows[t.ticker]).length;
    const total = allT.length;

    const tickerStats = allT.map(t => {
      const d = rows[t.ticker];
      if (!d || d.m3 == null) return { ticker: t.ticker, alpha: null };
      const relM3 = spyM3 != null ? d.m3 - spyM3 : d.m3;
      let relM1 = d.m1 != null ? (spyM1 != null ? d.m1 - spyM1 : d.m1) : null;
      const usedFallback = relM1 == null;
      if (usedFallback) relM1 = relM3;
      return { ticker: t.ticker, relM3, relM1, alpha: relM3 * 0.7 + relM1 * 0.3, usedFallback };
    });

    const loaded = tickerStats.filter(s => s.alpha != null);
    if (!loaded.length) {
      return { ...phase, score: null, breadth: null, dispersion: null, acceleration: accelInfo(null), tickerRanks: {}, loaded: dataCount, total };
    }

    const fallbackTickers = loaded.filter(s => s.usedFallback).map(s => s.ticker);
    // (aquí cycle.html escribe en la consola de depuración los tickers en fallback; no cambia el resultado)

    const alphas = loaded.map(s => s.alpha);
    const score = alphas.reduce((a, b) => a + b, 0) / alphas.length;
    const dispersion = stdev(alphas);
    const breadth = { pos: alphas.filter(a => a > 0).length, total: alphas.length, pct: Math.round(alphas.filter(a => a > 0).length / alphas.length * 100) };

    const relM3avg = loaded.reduce((a, s) => a + s.relM3, 0) / loaded.length;
    const relM1avg = loaded.reduce((a, s) => a + s.relM1, 0) / loaded.length;
    const prev2Mavg = (relM3avg - relM1avg) / 2;
    const acceleration = accelInfo(relM1avg - prev2Mavg);

    const ranked = [...loaded].sort((a, b) => b.alpha - a.alpha);
    const tickerRanks = {};
    ranked.forEach((s, i) => { tickerRanks[s.ticker] = { rank: i + 1, alpha: s.alpha }; });

    return { ...phase, score, breadth, dispersion, acceleration, tickerRanks, loaded: dataCount, total };
  });
}
function computeCycleSummary(classicPhases) {
  const scored = classicPhases.filter(p => p.score != null);
  const accelerated = classicPhases.filter(p => p.acceleration?.pp != null);
  if (!scored.length) return null;
  const dominant = [...scored].sort((a, b) => b.score - a.score)[0];
  const losing = [...scored].sort((a, b) => a.score - b.score)[0];
  const mostAccel = accelerated.length ? [...accelerated].sort((a, b) => b.acceleration.pp - a.acceleration.pp)[0] : null;
  const mostDecel = accelerated.length ? [...accelerated].sort((a, b) => a.acceleration.pp - b.acceleration.pp)[0] : null;
  return { dominant, losing, mostAccel, mostDecel };
}
module.exports = { CYCLE_MAP, accelInfo, stdev, calcPhaseScores, computeCycleSummary, ORIGINAL_SHA256, COPY_VERSION };
