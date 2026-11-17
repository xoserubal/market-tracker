"""Reglas oficiales de Alpaca sobre qué trades actualizan cada campo de una barra de 1 MINUTO.

Fuente: https://docs.alpaca.markets/us/docs/market-data-faq (tabla «stock bar update rules», updatedAt 2026-09-21),
basada en la guía CTS (cintas A/B), UTP (C) y TDDS (OTC, O). Valores: 'Y' actualiza, 'Y1' solo si es el primer
trade de la barra (open/close), 'N' no actualiza. Con varias condiciones se aplica la regla más estricta.
El nº de trades (n) de la barra sigue la regla de VOLUMEN.

Solo se codifican las reglas de barras de minuto (las diarias difieren en G, P, T, Z, 4, 9).
"""
# código -> {cinta: (open_close, high_low, volume)}; '*' = todas las cintas listadas
MINUTE_RULES = {
    " ": {"*": ("Y", "Y", "Y")},
    "@": {"*": ("Y", "Y", "Y")},
    "A": {"*": ("Y", "Y", "Y")},
    "B": {"A": ("N", "N", "Y"), "B": ("N", "N", "Y"), "C": ("Y", "Y", "Y"), "*": ("N", "N", "Y")},
    "C": {"*": ("N", "N", "Y")},
    "D": {"*": ("Y", "Y", "Y")},
    "E": {"*": ("Y", "Y", "Y")},
    "F": {"*": ("Y", "Y", "Y")},
    "G": {"*": ("N", "N", "Y")},
    "H": {"*": ("N", "N", "Y")},
    "I": {"*": ("N", "N", "Y")},
    "K": {"*": ("Y", "Y", "Y")},
    "L": {"*": ("Y", "Y", "Y")},
    "M": {"*": ("N", "N", "N")},
    "N": {"*": ("N", "N", "Y")},
    "O": {"*": ("Y", "Y", "Y")},
    "P": {"*": ("N", "N", "Y")},
    "Q": {"*": ("N", "N", "N")},
    "R": {"*": ("N", "N", "Y")},
    "T": {"*": ("Y", "Y", "Y")},
    "U": {"*": ("N", "N", "Y")},
    "V": {"*": ("N", "N", "Y")},
    "W": {"*": ("N", "N", "Y")},
    "X": {"*": ("Y", "Y", "Y")},
    "Y": {"*": ("Y", "Y", "Y")},
    "Z": {"*": ("N", "N", "Y")},
    "4": {"*": ("N", "N", "Y")},
    "5": {"*": ("Y", "Y", "Y")},
    "6": {"*": ("Y", "Y", "Y")},
    "7": {"*": ("N", "N", "Y")},
    "9": {"*": ("N", "N", "N")},
}
_RANK = {"N": 0, "Y1": 1, "Y": 2}

# condiciones de interés analítico (no afectan a las reglas)
EXTENDED_HOURS = {"T", "U"}
ODD_LOT = "I"
AUCTION = {"O", "Q", "5", "6", "M"}
NON_STANDARD_PRICE = {"B", "C", "G", "H", "N", "P", "R", "V", "W", "Z", "4", "7", "9"}


def minute_flags(conditions, tape: str):
    """Devuelve (oc, hl_bool, vol_bool, unknown_codes) aplicando la regla más estricta."""
    oc, hl, vol = "Y", "Y", "Y"
    unknown = []
    for code in (conditions or [" "]):
        rule = MINUTE_RULES.get(code)
        if rule is None:
            unknown.append(code)
            continue
        r = rule.get(tape) or rule["*"]
        oc = min(oc, r[0], key=_RANK.get)
        hl = min(hl, r[1], key=_RANK.get)
        vol = min(vol, r[2], key=_RANK.get)
    return oc, hl == "Y", vol == "Y", unknown
