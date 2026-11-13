# Estudio de primas — ETFs inversos

Snapshots: 20 día(s) (2026-10-12 → 2026-11-12). 

## UVXY — último snapshot 2026-11-12 (spot 17.35)

- IV ATM ~30d: **107%** · RV20: 192% · IV/RV20: **0.56** (percentil propio: 5)
- Plazos: IV ~90d 111% · ratio 3m/1m **1.04** (normal); días con curva invertida: 45% de 20
- Skew call−put ~30d: 33pp · spread bid-ask cerca del ATM: 22%

- **Carry implícito** (parity, 2027-01-15, 64 DTE, strike 17.0): forward 17.275 → deriva implícita **-0.4%** hasta el vencimiento (exceso sobre tipo libre -1.2% ≈ -7.0% anualizado)
  - Deriva histórica mediana a 44 sesiones: **-22.3%** (n=1463). La cadena implica menos caída que la histórica: hay hueco, con la cautela de que el pasado no garantiza.

**Estructura candidata (precios de la cadena, compra al ask / venta al bid):**
- Put spread 2027-01-15 (64 DTE): compra 15.0 / vende 11.0 → débito **1.97** (máx. ganancia 2.03; spread bid-ask de la pata comprada 19%)
- Call spread vendido 2026-12-18 (36 DTE): vende 24.0 / compra 32.0 → crédito **0.2** (pérdida máx. 7.8)

**Prima vs distribución histórica de retornos** (al vencimiento, sin gestión intermedia; NO es un backtest de opciones):
- Put spread, incondicional (n=1463): pago esperado 1.723 vs débito → EV neto **-0.247** (pago/débito 0.87), gana en el 45% de los casos
- Put spread, señal VIX>=25+giro (n=88): pago esperado 2.745 vs débito → EV neto **0.775** (pago/débito 1.39), gana en el 73% de los casos
- Call spread vendido, incondicional (n=1482): P&L esperado **0.121**, pérdida máxima en el 0% de los casos, peor caso -7.8
- Call spread vendido, señal VIX>=25+giro (n=88): P&L esperado **0.2**, pérdida máxima en el 0% de los casos, peor caso 0.2

## SQQQ — último snapshot 2026-11-12 (spot 40.93)

- IV ATM ~30d: **72%** · RV20: 104% · IV/RV20: **0.70** (percentil propio: 10)
- Plazos: IV ~90d 72% · ratio 3m/1m **1.00** (invertida); días con curva invertida: 45% de 20
- Skew call−put ~30d: 23pp · spread bid-ask cerca del ATM: 15%

- **Carry implícito** (parity, 2027-01-15, 64 DTE, strike 41.0): forward 40.5 → deriva implícita **-1.1%** hasta el vencimiento (exceso sobre tipo libre -1.8% ≈ -10.0% anualizado)
  - Deriva histórica mediana a 44 sesiones: **-13.0%** (n=1463). La cadena implica menos caída que la histórica: hay hueco, con la cautela de que el pasado no garantiza.

**Estructura candidata (precios de la cadena, compra al ask / venta al bid):**
- Put spread 2027-01-15 (64 DTE): compra 36.0 / vende 25.0 → débito **2.45** (máx. ganancia 8.55; spread bid-ask de la pata comprada 12%)
- Call spread vendido 2026-12-18 (36 DTE): vende 55.0 / compra 80.0 → crédito **0.61** (pérdida máx. 24.39)

**Prima vs distribución histórica de retornos** (al vencimiento, sin gestión intermedia; NO es un backtest de opciones):
- Put spread, incondicional (n=1463): pago esperado 2.539 vs débito → EV neto **0.089** (pago/débito 1.04), gana en el 38% de los casos
- Call spread vendido, incondicional (n=1482): P&L esperado **0.448**, pérdida máxima en el 0% de los casos, peor caso -15.208

## GLL — último snapshot 2026-11-12 (spot 28.59)

- IV ATM ~30d: **55%** · RV20: 56% · IV/RV20: **0.98** (percentil propio: 10)
- Plazos: IV ~90d 53% · ratio 3m/1m **0.97** (invertida); días con curva invertida: 35% de 20
- Skew call−put ~30d: -6pp · spread bid-ask cerca del ATM: 50%

- Carry implícito: no calculable (faltan cotizaciones call/put en el ATM de ~90 DTE).

**Estructura candidata (precios de la cadena, compra al ask / venta al bid):**
- Put spread 2027-01-15 (64 DTE): compra 27.0 / vende 17.0 → débito **1.7** (máx. ganancia 8.3; spread bid-ask de la pata comprada 26%)
- Call spread vendido: sin cotizaciones utilizables a ~30 DTE.

**Prima vs distribución histórica de retornos** (al vencimiento, sin gestión intermedia; NO es un backtest de opciones):
- Put spread, incondicional (n=1463): pago esperado 1.336 vs débito → EV neto **-0.364** (pago/débito 0.79), gana en el 33% de los casos

## BOIL — último snapshot 2026-11-12 (spot 19.76)

- IV ATM ~30d: **117%** · RV20: 65% · IV/RV20: **1.81** (percentil propio: 90)
- Plazos: IV ~90d 118% · ratio 3m/1m **1.01** (normal); días con curva invertida: 5% de 20
- Skew call−put ~30d: 13pp · spread bid-ask cerca del ATM: 16%

- **Carry implícito** (parity, 2027-01-15, 64 DTE, strike 20.0): forward 19.7 → deriva implícita **-0.3%** hasta el vencimiento (exceso sobre tipo libre -1.1% ≈ -6.0% anualizado)
  - Deriva histórica mediana a 44 sesiones: **-14.8%** (n=1463). La cadena implica menos caída que la histórica: hay hueco, con la cautela de que el pasado no garantiza.

**Estructura candidata (precios de la cadena, compra al ask / venta al bid):**
- Put spread 2027-01-15 (64 DTE): compra 17.0 / vende 12.0 → débito **2.41** (máx. ganancia 2.59; spread bid-ask de la pata comprada 16%)
- Call spread vendido 2026-12-18 (36 DTE): vende 25.0 / compra 37.0 → crédito **0.81** (pérdida máx. 11.19)

**Prima vs distribución histórica de retornos** (al vencimiento, sin gestión intermedia; NO es un backtest de opciones):
- Put spread, incondicional (n=1463): pago esperado 1.821 vs débito → EV neto **-0.589** (pago/débito 0.76), gana en el 38% de los casos
- Call spread vendido, incondicional (n=1482): P&L esperado **0.052**, pérdida máxima en el 2% de los casos, peor caso -11.19

---
Notas: umbrales y strikes (85%/60% put, 130%/200% call) de primera pasada, sin calibrar. Con pocos días de snapshots los percentiles y el % de curva invertida no son concluyentes. El valor esperado usa retornos reales del ETF, pero ignora la gestión intermedia, el early exercise y los costes de comisión. Las muestras son días solapados (ventanas de 21-63 sesiones): el n efectivo es mucho menor que el n nominal, y los eventos con señal se agrupan en pocos episodios.
