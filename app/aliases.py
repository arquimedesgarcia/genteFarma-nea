"""Alias de ESCRITURA de medicamentos (F14.4).

Por qué existe
--------------
El motor del catálogo es difuso por diseño: tolera typos con Levenshtein ≤2 y
prefijos. Eso es lo que hace funcionar 'diclofencao' → DICLOFENAC, pero también
es lo que hace que un término mal escrito salte de CATEGORÍA TERAPÉUTICA:
medido en el caso real del cliente,

    'vivacina' → VITAMINA K y VITAMINA C   (distancia de edición 2)

El cliente pedía (probablemente) otra cosa y recibió vitaminas. Cuando la
ortografía correcta se CONOCE, no hay por qué dejar que el matcher adivine: se
reescribe el término ANTES de buscar y se apaga la tolerancia a typos para esa
búsqueda. El catálogo encuentra el nombre canónico por coincidencia literal.

REGLA DE ORO — qué NO entra aquí
--------------------------------
1. NUNCA marca → principio activo (MACRODANTINA → NITROFURANTOINA). Eso ya lo
   hace `_buscar_por_principio_activo` en tools.py, y una reescritura forzada
   ESCONDERÍA el producto de marca cuando el catálogo sí lo tiene.
2. NUNCA pares con final ambiguo en español (amlodipina/amlodipino,
   ciprofloxacina/ciprofloxacino): la reescritura desactiva el fuzzy, así que
   una grafía canónica equivocada devuelve CERO resultados.
3. Solo variantes ORTOGRÁFICAS del mismo nombre, con la grafía canónica
   verificable (la que usa el catálogo / el INN estándar).

Fail-safe en tools.py: si la búsqueda con el alias reescrito devuelve 0
productos, se REINTENTA con el término original (con fuzzy). Un alias solo
puede ayudar; nunca puede esconder un resultado.

Fuentes de la semilla (ver migrations/013_med_aliases.sql):
  - `med_queries` (log real de consultas sin resultados) → pares typo→grafía
    usada después en la misma conversación.
  - Casos reales verificados por simulación (docs/F14-diagnostico-busqueda.md).
  - Comentarios medidos del propio código (relevancia.py / tools.py).
"""
from __future__ import annotations

import logging
import re
from typing import Any, Iterable

logger = logging.getLogger("nea.aliases")

# --------------------------------------------------------------------- claves ---

_SIN_TILDES = (
    ("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u"),
    ("à", "a"), ("è", "e"), ("ì", "i"), ("ò", "o"), ("ù", "u"), ("ñ", "n"),
)

# Unidades/dosis y FORMA farmacéutica que pueden seguir al alias sin romper la
# coincidencia ("solunoval 500 mg" → "solunovar 500 mg"; "solunoval solución
# bucal" → "solunovar solucion bucal"). Lo que NO puede seguir es otra palabra
# de fármaco: ahí el alias no aplica (sería reescribir una frase distinta).
_DOSIS = {
    "mg", "ml", "mcg", "g", "gr", "gramos", "mili", "miligramos", "ui", "cc",
    "tab", "tabs", "tableta", "tabletas", "cap", "caps", "capsula", "capsulas",
    "jarabe", "jbe", "crema", "gel", "spray", "gotas", "solucion", "suspension",
    "pomada", "unguento", "ampolla", "ampollas", "inyectable", "ovulo", "ovulos",
    "supositorio", "sobre", "sobres", "x", "hp", "retard", "forte", "fuerte",
    "bucal", "oral", "topico", "nasal", "oftalmico", "otico", "vaginal",
    "rectal", "pediatrico", "adulto", "infantil", "grageas", "comprimidos",
    "recubiertos", "polvo", "liquido", "emulsion", "locion", "colirio", "plus",
}

# Letras de vitamina: pueden seguir al alias sin romper la coincidencia
# ('bitamina c' → 'vitamina c').
_LETRAS_VITAMINA = {"a", "b", "c", "d", "e", "k"}


def _clave(termino: str) -> str:
    """Clave de comparación: minúsculas, sin tildes, espacios colapsados."""
    t = str(termino or "").lower().replace(".", " ").replace(",", " ")
    for a, b in _SIN_TILDES:
        t = t.replace(a, b)
    t = re.sub(r"[^a-z0-9\s]", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# ------------------------------------------------------------------ registro ---

# alias normalizado → grafía canónica (tal como se pasa al catálogo).
_ALIASES: dict[str, str] = {}


def cargar_items(items: Iterable[Any]) -> int:
    """Carga pares alias→canónico (dicts con 'alias'/'canonico' o tuplas).

    Devuelve cuántos pares quedaron en el registro. Idempotente.
    """
    n = 0
    for it in items or []:
        if isinstance(it, dict):
            alias = it.get("alias") or it.get("term")
            canon = it.get("canonico") or it.get("canonical")
        elif isinstance(it, (tuple, list)) and len(it) >= 2:
            alias, canon = it[0], it[1]
        else:
            continue
        if registrar(str(alias or ""), str(canon or "")):
            n += 1
    return n


def registrar(alias: str, canonico: str) -> bool:
    """Registra UN par. Ignora pares vacíos o idénticos (no aportan nada)."""
    a, c = _clave(alias), _clave(canonico)
    if not a or not c or a == c:
        return False
    _ALIASES[a] = c
    return True


def limpiar() -> None:
    """Vacía el registro (tests / recarga)."""
    _ALIASES.clear()


def total() -> int:
    return len(_ALIASES)


def tabla() -> dict[str, str]:
    """Copia del registro (diagnóstico / reportes)."""
    return dict(_ALIASES)


# ------------------------------------------------------------------- consulta ---

def _resto_es_dosis(resto: str) -> bool:
    """¿El resto tras el alias son solo dosis/unidades/números?

    'solunoval 500 mg' → resto '500 mg' → True (el alias aplica).
    'vitamina c de la opcion 9' → resto con palabras de fármaco → False.

    Las LETRAS DE VITAMINA (c, d, e, k, b) cuentan como resto válido: sin esto
    el alias 'bitamina' no aplicaría a 'bitamina c', que es la forma en que el
    cliente lo escribe.
    """
    tokens = [t for t in resto.split() if t]
    if not tokens:
        return True
    return all(t.isdigit() or t in _DOSIS or t in _LETRAS_VITAMINA for t in tokens)


def es_alias(termino: str) -> bool:
    """True si el término (solo o con dosis) es un alias conocido."""
    return alias_de(termino) is not None


def alias_de(termino: str) -> tuple[str, str] | None:
    """Devuelve (canónico, alias) si el término coincide con un alias conocido."""
    clave = _clave(termino)
    if not clave:
        return None
    if clave in _ALIASES:
        return _ALIASES[clave], clave
    # Alias + dosis/presentación ("solunoval 500 mg"). Se toma el alias MÁS
    # LARGO que coincida como prefijo de palabras completas.
    mejor: tuple[str, str] | None = None
    for alias, canon in _ALIASES.items():
        if " " in alias:
            # Un alias de varias palabras solo aplica por prefijo de texto.
            if clave.startswith(alias + " ") and _resto_es_dosis(clave[len(alias):]):
                if mejor is None or len(alias) > len(mejor[1]):
                    mejor = (canon, alias)
            continue
        if not clave.startswith(alias + " "):
            continue
        if not _resto_es_dosis(clave[len(alias):]):
            continue
        if mejor is None or len(alias) > len(mejor[1]):
            mejor = (canon, alias)
    return mejor


def reescribir(termino: str) -> tuple[str, bool]:
    """Reescribe el término si es (o empieza por) un alias conocido.

    Devuelve (término_final, fue_alias). Con dosis detrás, la conserva:
    'solunoval 500 mg' → ('solunovar 500 mg', True).
    """
    original = str(termino or "").strip()
    par = alias_de(original)
    if par is None:
        return original, False
    canon, alias = par
    clave = _clave(original)
    resto = clave[len(alias):].strip()
    nuevo = f"{canon} {resto}".strip() if resto else canon
    logger.info("alias: '%s' → '%s'", original, nuevo)
    return nuevo, True


async def cargar_desde_store(store: Any) -> int:
    """Carga la tabla `med_aliases` del store al registro en memoria (arranque).

    Nunca lanza: los alias son una mejora, jamás un requisito para atender un
    turno. Si la tabla no existe (migración no aplicada) o está vacía, se
    registra el aviso y el agente sigue con el comportamiento de siempre.
    """
    try:
        rows = await store.list_med_aliases()
    except Exception:
        logger.warning("aliases: no se pudo leer med_aliases — sigo sin alias")
        return 0
    n = cargar_items(rows)
    if n:
        logger.info("aliases: %d pares cargados de med_aliases", n)
    else:
        logger.warning(
            "aliases: med_aliases vacía — sin reescritura de typos "
            "(¿migración 013_med_aliases.sql aplicada?)"
        )
    return n

