# GEX (dealer gamma exposure) — piloto, 2026-08-18

**Estado: no integrado.** Ver `CLAUDE.md`, sección "GEX (dealer gamma
exposure) — piloto, no integrado (2026-08-18)" para el resumen corto.

## Origen

Un análisis externo, revisando el contexto de `duration.html`, señaló que
para saber si un "desanclaje" (de tipos/expectativas) es fuerte o trivial
hace falta saber el posicionamiento de gamma de los dealers (largo vs corto)
— dato que este proyecto no tenía. Se acordó con el usuario: montar un
piloto DIY (opciones vía yfinance + Black-Scholes), verificarlo contra un
caso real, y decidir si vale la pena incorporarlo antes de tocar
`duration.html`/`positioning.html`.

## Qué se construyó

`gex_pilot.py` — descarga la cadena de opciones de `^SPX` (índice, no SPY;
verificado que yfinance sí sirve 53 vencimientos con OI/IV reales para
`^SPX`, no solo para ETFs), calcula Gamma de Black-Scholes por contrato
(r=q=0), y agrega:

```
GEX_contrato = Gamma × OpenInterest × 100 × Spot² × 0.01
Net GEX = Σ(GEX calls) − Σ(GEX puts)
```

Convención estándar de la mayoría de explicadores públicos de GEX (dealers
asumidos largos en las calls que compran los clientes, cortos en las puts
que compran los clientes — ver
[perfiliev.com](https://perfiliev.com/blog/how-to-calculate-gamma-exposure-and-zero-gamma-level/)).
También calcula el nivel de "gamma flip" (zero-gamma) barriendo precios de
spot hipotéticos y buscando el cruce por cero de Net GEX.

## Verificación — resultado matizado, no un simple "funciona"/"no funciona"

**Primer intento de comparación (engañoso):** se comparó el resultado del
piloto (2026-08-18, spot=7701.37, Net GEX=-$53.06B) contra un snapshot de
[flashalpha.com/stock/spx](https://flashalpha.com/stock/spx) obtenido por
búsqueda (Net GEX=+$87.6B, spot=7788.43, timestamp "Aug 17, 2026 1:31 PM
ET"). Signo opuesto — la primera conclusión (equivocada) fue "la
metodología está rota".

**Corrección tras mirar el nivel de gamma flip, no solo el signo:**
FlashAlpha reporta flip=$7,739. El piloto calculó flip=$7,746.7 —
~0.1% de diferencia, notablemente cercano pese a ser cálculos
independientes. Si el flip real está en esa zona (~7739-7747), el signo de
Net GEX depende únicamente de qué lado del flip esté el spot en cada
momento — y el spot real de SPX cayó de forma continua en esos días:
7785.76 (14/8) → 7745.06 (17/8, cierre) → 7701.87 (18/8) — cruzando
exactamente esa zona. El signo distinto entre los dos snapshots es
coherente con un movimiento real de mercado atravesando el flip, no
necesariamente con una metodología equivocada.

**Pero el propio benchmark resultó no ser fiable para comparar en igualdad
de condiciones:** al recontrastar el spot que dice FlashAlpha (7788.43 "a
las 13:31 ET del 17/8") contra el histórico intradía real de Yahoo para
`^SPX` en esa misma franja horaria (barras de 30 min: 13:00→7756.40,
13:30→7754.71), hay un desajuste de ~30-35 puntos (~0.4%) que no encaja con
ninguna barra real de ese día. Dos fetches de la misma página con varios
minutos de diferencia devolvieron contenido idéntico (posible caché del
lado de FlashAlpha, o página de ejemplo no verdaderamente en vivo) — no se
pudo confirmar que ese número fuera un dato fresco al momento de
consultarlo, así que tampoco es un benchmark limpio para validar signo o
magnitud.

## Conclusión

1. El cálculo en sí (Black-Scholes + convención estándar) está implementado
   correctamente y corre de punta a punta sobre datos reales de mercado
   (`^SPX`, 30 vencimientos, ~10.000 contratos, spot y cadena descargados en
   vivo).
2. El nivel de gamma flip calculado es plausible y razonablemente cercano
   al de un proveedor externo — la única señal de validación medianamente
   sólida obtenida.
3. **No se encontró ninguna fuente gratuita con datos verificablemente en
   vivo** contra la que contrastar signo/magnitud con confianza — las
   páginas "gratis" de proveedores de GEX no se pudieron confirmar como
   realmente frescas al momento de la consulta automatizada.
4. Limitación estructural, no de implementación: la convención "toda la OI
   de puts es venta de dealers a clientes" es una aproximación — el dato
   real (desglose customer/firm/market-maker de la OCC) que distinguiría
   put-OI vendida a dealers de put-OI comprada por dealers no está
   disponible gratis (Cboe Options Open-Close Volume Summary es un
   producto de pago en DataShop).

**Recomendación:** no integrar en `duration.html`/`positioning.html` como
señal de confianza. A diferencia del proxy de MOVE en `duration.html`
(calibrado con 5 años de histórico real de `^MOVE` para contrastar) o
`calcAtlasMini`/`calcCMF` (fórmulas deterministas sin ambigüedad de
convención), aquí no hay forma barata de saber si el número que sale hoy es
correcto. Mismo principio que rige el resto del proyecto: no añadir
complejidad — ni mostrar un número al usuario — sin poder verificarlo.

## Cómo reproducir

```bash
cd research/gex_monitor_pilot
py -3 gex_pilot.py                    # ^SPX, horizonte 60 días
py -3 gex_pilot.py --ticker ^SPX --horizon-days 30 --no-save
```

## Por qué queda aquí y no se borra

Documenta un caso real de por qué "el signo no coincide con un proveedor
externo" no es automáticamente "está roto" (el flip level sí coincidía) —
y por qué "no encontré un benchmark gratis fiable" es en sí mismo un
hallazgo válido, no una excusa para no verificar. Si en el futuro aparece
una fuente de datos con desglose customer/firm real (de pago o no), este
script es reutilizable como base de cálculo — solo cambiaría qué OI se
etiqueta como "dealer short" vs "dealer long" por strike.

No se usa en producción. No toca `paper_trading.py`, `pcs_calculator.py`,
ninguna cartera, `duration.html` ni `positioning.html`.
