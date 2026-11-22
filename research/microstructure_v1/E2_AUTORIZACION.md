# Autorización de E2 (usuario, 2026-11-21)

Texto literal recibido en el chat. Lanzar el cálculo pesado de E2 cuando termine la tanda 2 de Flow negativo
(mismo equipo, LAWNMOWER: 16 GB de RAM).

---

He revisado E1_INFORME.md.

**APRUEBO E1 Y AUTORIZO LA EJECUCIÓN DE E2**, con las siguientes precisiones.

### 1. Objetivo de E2

Continuar con la caracterización estadística y calibración del registro de eventos intradía.

No buscar alfa todavía, no calcular resultados posteriores a los acontecimientos y no convertir las anomalías en señales automáticas de compra o venta.

### 2. Período y universo

Apruebo usar exclusivamente el histórico disponible de 2016 a 2021-10-28, con miembros verificados del S&P 500 a cada fecha.

Mantener bloqueado el conjunto reservado de G2A.

Calibrar umbrales utilizando 2016-2019 y comprobar su estabilidad sobre 2020-2021 sin reajustarlos posteriormente en ese segundo período.

Resolver correctamente el calentamiento inicial de las líneas base y contar siempre los denominadores elegibles.

### 3. Normalización incremental

Apruebo implementar la normalización estrictamente point-in-time.

Cada fecha debe evaluarse con información anterior a ella, manteniendo separadas las franjas horarias y los tipos de negociación.

Compara diferentes alternativas de referencia:
- Ventana móvil ordinaria.
- Medidas robustas frente a valores extremos.
- Adaptación progresiva a cambios de régimen.

No excluyas automáticamente de la línea base los días que generaron alertas, porque eso podría impedir que el detector reconozca cambios persistentes de régimen.

### 4. Calibración del catálogo

La regla actual «percentil extremo O z robusto ≥ 4» necesita revisión.

Evalúa la frecuencia de falsas anomalías de medidas con MAD pequeña y las distribuciones de rachas, cocientes y variables próximas a cero.

Utiliza transformaciones o criterios específicos por familia cuando estén justificados.

Mide las frecuencias tanto por medida como por valor-día, episodio, familia y segmento horario.

El objetivo orientativo del 1-3 % no es una cuota obligatoria. En días extraordinarios o de estrés generalizado debe ser posible detectar numerosos eventos simultáneos.

Conserva todas las medidas brutas y normalizadas, independientemente de los umbrales elegidos.

### 5. Priorización y agrupación

Distingue y conserva por separado:

- Rareza estadística.
- Magnitud del movimiento o volumen.
- Simultaneidad con el mercado y sector.
- Persistencia.
- Calidad del dato.

No generes todavía un score predictivo.

Analiza las redundancias entre medidas y corrige la fusión excesiva de episodios que terminan abarcando sesiones enteras.

Conserva las alertas originales aunque se agrupen.

### 6. Petición múltiple de barras

Autorizo añadirla al proveedor para reducir llamadas.

Antes de usarla a escala, verifica equivalencia con las peticiones individuales, paginación, cobertura de cada símbolo, tratamiento de símbolos ausentes y recuperación de errores parciales.

Mantén el limitador compartido, las comprobaciones de calidad y la idempotencia.

### 7. Código de captura anterior

Declara `micro/shadow.py` como obsoleto para esta línea de eventos y mantenlo desactivado.

No lo elimines hasta comprobar que ninguna parte del proyecto depende de él y que el nuevo sistema cubre sus responsabilidades.

El fallo detectado en las unidades de sesión debe quedar corregido también en cualquier ruta de descarga reutilizable.

### 8. Descargas

No reanudes de momento el nivel A completo. Los datos necesarios para el retrospectivo de E2 ya están disponibles.

No descargues trades y quotes masivamente. El desglose debe continuar bajo demanda y en muestras acotadas.

### 9. Entregables

Quiero:

- Frecuencia de eventos por medida, familia, año, liquidez y tramo horario.
- Análisis de redundancia, persistencia y simultaneidad.
- Distribución de longitudes de los episodios.
- Comparación de métodos de normalización.
- Propuesta justificada de catálogo `cat-v1`.
- Estabilidad de las frecuencias fuera del período de calibración.
- Muestra aleatoria estratificada de eventos y ventanas sin anomalías, inspeccionables en el laboratorio.
- Reestimación de costes de almacenamiento y procesamiento.
- Informe de limitaciones.

El catálogo `cat-v0` y sus resultados deben permanecer reproducibles.

**Completa E2 y detente para mi aprobación antes de cambiar a `cat-v1` o activar E3.**

No actives ninguna tarea programada ni el registro diario en sombra. No modifiques producción ni hagas commits, push o merge sin autorización.
