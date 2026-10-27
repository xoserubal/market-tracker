"""Resuelve el campo libre `subject` de las señales de Sol a instrumentos medibles.

Reglas (fijadas antes de mirar retornos):
- Se tokeniza el subject por separadores (/ , y vs). Cada token se busca primero en
  ALIASES (nombres -> ticker) y después como ticker literal si cumple el patron.
- Para "A vs B": se mide solo la pata A (lado izquierdo de 'vs'); la B es referencia.
- Cesta = media simple de los tickers resueltos del lado largo; el primer token es el 'primary'.
- Si no se resuelve ningun ticker -> no medible (se cuenta aparte).
"""
import re

ALIASES = {
    'btc': 'BTC-USD', 'bitcoin': 'BTC-USD', 'btc-usd': 'BTC-USD',
    'uranium complex': 'URNM', 'uranio': 'URNM', 'uranium': 'URNM',
    'nasdaq': 'QQQ', 'wti': 'CL=F', 'brent': 'BZ=F', 'gold': 'GC=F', 'oro': 'GC=F',
    'silver': 'SI=F', 'plata': 'SI=F', 'semiconductores': 'SMH', 'real yields': None,
    '10y': None, 'yields': None, 'vix': None, 'hy spreads': None, 'fed net liquidity': None,
    'ag': 'AG', 'exk': 'EXK', 'u-u.to': 'U-U.TO',
    'spx': '^GSPC', 'ftse': '^FTSE', 'cac': '^FCHI', 'dax': '^GDAXI', 'aex': '^AEX', 'ibex': '^IBEX',
    'fdr': None, 'bnkr': None, 'se': None, 'sls': None, 'ie': None, 'medtech': None, 'carbón': None,
    'fez': 'FEZ', 'sectores europeos': None, 'productores': None,
    'carbón metalúrgico': None, 'carbon metalurgico': None,
    'líderes de carbón': None, 'data feeds': None, 'complex': None,
}
TICKER_RE = re.compile(r'^\^?[A-Z][A-Z0-9]{0,5}([.\-=][A-Z0-9]{1,3})?$')
STOP = {'Y','VS','THE','DE','LA','DEL'}

def split_subject(subj):
    subj = subj.split(':',1)[-1] if ':' in subj else subj
    left = re.split(r'\s+vs\.?\s+|\s+frente a\s+', subj, flags=re.I)[0]
    toks = re.split(r'\s*/\s*|\s*,\s*|\s+y\s+|\s+\+\s+', left)
    return [t.strip() for t in toks if t.strip()]

def resolve(subj):
    out = []
    for t in split_subject(subj):
        key = t.lower()
        if key in ALIASES:
            if ALIASES[key]: out.append(ALIASES[key])
            continue
        # ticker literal (permitir 'MU', '^GSPC', 'EOS.AX', 'NG=F', 'U-U.TO')
        cand = t.split()[0]
        if cand.upper() not in STOP and TICKER_RE.match(cand):
            out.append(cand)
    seen = []; [seen.append(x) for x in out if x not in seen]
    return seen
