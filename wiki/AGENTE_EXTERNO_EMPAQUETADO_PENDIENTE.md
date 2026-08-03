# Cava AI → AI Picks Lab — Tres cosas del empaquetado antes del cierre real

> Al conectar el paquete al pipeline nos hemos encontrado con tres puntos que
> impiden el `pip install` acordado. Ninguno afecta al motor —que funciona
> perfectamente, la Prueba 1C se ejecutó con él— y **no nos estáis bloqueando**:
> tenemos una vía alternativa ya probada. Pero conviene cerrarlos para que quede
> como estaba diseñado.
>
> Los tres son de arreglo rápido y os damos el código concreto.

---

## 1. La URL del repositorio no existe

Nos pasasteis `https://github.com/cava-ai/decision-engine.git`. Esa organización
devuelve 404: no existe.

El paquete **sí está publicado**, y donde tocaba — en el repositorio privado del
cliente:

```
xoserubal/cava-decision-engine        (privado, rama main)
```

Suponemos que la URL salió del campo `Homepage` del `pyproject.toml`, que apunta
a `cava-ai/decision-engine`. Conviene corregirlo ahí también para que no vuelva a
despistar a nadie.

---

## 2. No existe el tag `v1.1.0`

El repositorio solo tiene la rama `main`, sin ningún tag publicado.

Toda la disciplina de versionado que acordamos en la Ronda 2 se apoyaba en fijar
un tag concreto y no instalar nunca desde `main`. Sin tag no se puede hacer.

**Mientras tanto lo hemos resuelto fijando el commit:**

```
6b4fd1bc5f01460969fc3d0ef355f1cf6960da59
```

Un SHA cumple el mismo propósito e incluso mejor —un tag se puede mover, un
commit no—, así que no es urgente. Pero un `v1.1.0` es más legible en los
registros, y vamos a guardar la versión junto a cada decisión de la cartera.

---

## 3. El paquete no se puede instalar con `pip` — y este sí importa

Es el que rompe la arquitectura acordada, porque todo el planteamiento in-process
dependía de que GitHub Actions pudiera hacer `pip install`.

Son dos problemas encadenados. El segundo es el de fondo.

### 3.1 `pyproject.toml` no declara el paquete

`setuptools` encuentra tres directorios de primer nivel (`cava_engine`, `corpus`,
`tests`) y se niega a adivinar cuál empaquetar:

```
error: Multiple top-level packages discovered in a flat-layout
Getting requirements to build wheel did not run successfully.
```

### 3.2 La ruta del corpus asume un clon del repositorio, no un paquete instalado

En `cava_engine/core.py`:

```python
WORKSPACE  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CORPUS_DIR = os.path.join(WORKSPACE, "corpus")
```

Sube un nivel desde `cava_engine/` para buscar `corpus/`. En un checkout del
repositorio funciona. Instalado con `pip`, `__file__` pasa a estar en
`site-packages/cava_engine/`, así que buscaría `site-packages/corpus` — un
directorio que no se crea nunca.

**Es decir: aunque se arreglara el punto 3.1, el paquete instalado no encontraría
el corpus.** Los dos van juntos.

### El arreglo (unos minutos)

**a)** Mover `corpus/` dentro del paquete: `cava_engine/corpus/`.

**b)** Resolver la ruta desde el propio módulo, sin subir niveles:

```python
CORPUS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "corpus")
```

**c)** Declarar paquete y datos en `pyproject.toml`:

```toml
[tool.setuptools]
packages = ["cava_engine"]

[tool.setuptools.package-data]
cava_engine = ["corpus/*.json"]
```

**d)** Publicar el tag `v1.1.0`.

### Cómo comprobar que quedó bien

La prueba que lo cierra, y que os recomendamos hacer antes de avisarnos:

```bash
python -m venv /tmp/prueba && /tmp/prueba/bin/pip install \
  "git+https://<token>@github.com/xoserubal/cava-decision-engine.git@v1.1.0"

cd /   # ← desde un directorio cualquiera, no desde el repo
/tmp/prueba/bin/python -c "from cava_engine import load_corpus; \
  print(len(load_corpus('pilot_incremental')[2]))"
```

Debe imprimir `112` **ejecutando desde fuera del repositorio**. Ese "desde fuera"
es la clave: es justo lo que hoy falla y lo que hará GitHub Actions.

---

## 4. Qué hacemos entretanto

No os esperamos. Vamos a **clonar el repositorio fijado al SHA de arriba y
añadirlo al `PYTHONPATH`** en el workflow, en vez de instalarlo.

Ya está verificado de extremo a extremo: el clon carga los 112 frames y devuelve
`reduce_risk` para el 8 de abril de 2025, idéntico a la copia local con la que
corrimos la Prueba 1C. Se conserva el determinismo y el pin deliberado de
versión; solo cambia el mecanismo de instalación.

Cuando publiquéis el arreglo, pasar de `git clone` a `pip install` es cambiar una
línea del workflow.

---

## 5. Resumen

| | Qué | Bloquea |
|---|---|---|
| 1 | URL correcta: `xoserubal/cava-decision-engine` | No |
| 2 | Publicar tag `v1.1.0` | No |
| 3 | `corpus/` dentro del paquete + ruta relativa al módulo + `pyproject.toml` | No (con la alternativa) |

Nada de esto afecta al motor ni a los resultados: la Prueba 1C se ejecutó contra
este mismo código y los números son válidos. Es la última milla del empaquetado.
