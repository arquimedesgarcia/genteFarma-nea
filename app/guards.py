"""Guardas deterministas anti-alucinación (rama agent-qa, T4 del plan QA).

Por qué existen: el Laboratorio demostró (baseline 29/100 y controles A2/B2
14/100) que la alucinación es CROSS-MODEL — 14B, 7B y LongCat inventan
precios, políticas y "recibí tu foto". Es un problema de ARQUITECTURA, no del
modelo: donde ya existía una guarda determinista (ver_carrito, catálogo
forzado, precio inventado) el agente no falla. Este módulo replica ese patrón
para los tres huecos restantes + hostilidad.

Cada guarda es CÓDIGO, no generación libre: detecta (regex determinista) y
reemplaza por plantilla constante. Cada activación se loguea con el prefijo
"guarda G#" para el conteo de vetos del reporte QA.
"""
from __future__ import annotations

import re
import unicodedata

# ---------------------------------------------------------------------------
# G1 — Precio sin dato real
# ---------------------------------------------------------------------------
# El cliente pregunta un precio y la conversación NO tiene respaldo del
# catálogo (runtime.last_products vacío). El LLM rellena con números inventados.
PIDE_PRECIO = re.compile(
    r"\b(precio[s]?\b|cu[aá]nto\s+(cuesta|vale|sale|es)|a\s+c[óo]mo\s+(est[áa]|sale)|"
    r"cu[aá]nto\s+me\s+(sale|costar[íi]a|ser[íi]a)|me\s+cuesta)\b",
    re.I,
)

TPL_SIN_PRECIO = (
    "Lo siento, no tengo un precio confirmado de eso en este momento y no "
    "quiero darte un número equivocado. Te puedo comunicar con un asistente "
    "de la farmacia para que te lo confirme. ¿Lo deseas?"
)

# ---------------------------------------------------------------------------
# G2 — Intención fuera del knowledge base (políticas de negocio)
# ---------------------------------------------------------------------------
# Temas que el agente NO puede resolver con sus herramientas (catálogo,
# carrito, pedido): el LLM inventa políticas de devolución/reclamo. Respuesta
# de escalado HARDCODEADA + handoff; jamás generación libre.
FUERA_KB = re.compile(
    r"\b(devoluci[óo]n|devolver|devuelv|reclam[oa]|garant[íi]a|reembols|"
    r"vencid[oa]|pol[íi]tic|dinero de vuelta|me lo cambian|hacen? (una )?(entrega|domicilio)|"
    r"env[íi]o a domicilio)",
    re.I,
)

TPL_FUERA_KB = (
    "Eso está fuera de lo que puedo resolver por este medio y no quiero "
    "darte información incorrecta. Te comunico con un asistente de la "
    "farmacia para que te responda con precisión."
)

# ---------------------------------------------------------------------------
# G3 — Canal sin media: prohibido afirmar que llegó una foto
# ---------------------------------------------------------------------------
# El agente decía "Recibí tu foto de receta" cuando NO llegó ninguna imagen
# (sin OCR y sin adjunto). Señal inyectada al prompt + veto post-generación.
MEDIA_MENCION = re.compile(
    r"\b(foto|fotos|imagen|im[áa]genes|adjunt|escane|captura)\b", re.I
)

CLAIM_RECIBIO_MEDIA = re.compile(
    r"(recib[íi]|me\s+lleg[óo]|vi|revis[ée]|ley[ée]|abrier?on?|tengo)\s+(tu|la|su|el)?\s*"
    r"(foto|imagen|adjunto|receta\s+en\s+(foto|imagen))|"
    r"(tu|la)\s+(foto|imagen)\s+(que\s+enviaste|de\s+la\s+receta|de\s+tu\s+receta)",
    re.I,
)

NO_MEDIA_ALERT = (
    "RESTRICCIÓN DEL CANAL (no la escribió el lead): este canal NO tiene "
    "media entrante en este turno. Si el lead menciona una foto, receta en "
    "imagen o adjunto, NO afirmes haberla recibido ni describirla: no existe. "
    "Pídele que escriba los medicamentos como TEXTO (nombre + miligramaje) y "
    "ayúdalo con el catálogo."
)

TPL_SIN_MEDIA = (
    "No me llegó ninguna imagen por este canal — aquí solo me llega texto. "
    "Escríbeme el nombre de los medicamentos (con el miligramaje si lo "
    "tienes) y te digo al instante qué tenemos disponible."
)

# ---------------------------------------------------------------------------
# G4 — Hostilidad: acusación de fraude → escalado inmediato
# ---------------------------------------------------------------------------
# hostility.py ya garantiza handoff al 3er strike. La acusación de fraude
# ("estafa", "ladrón") es el caso donde UN solo mensaje ya rompe la confianza
# y el bench mostró al agente "vendiendo" o negándose sin escalar.
ACUSACION_FRAUDE = re.compile(
    r"\b(estafa|estafador(?:es)?|est[áa]n\s+estafando|ladron(?:es|a|as)?|fraude|"
    r"me\s+quieren\s+robar|es\s+una\s+mentira|puro\s+humo)\b",
    re.I,
)

# Cierre constante de G4: NO lo redacta el LLM (en el bench generaba cierres
# débiles tipo "lamento tu experiencia"). Plantilla fija + handoff inmediato.
TPL_CIERRE_G4 = (
    "Entiendo tu molestia y la tomo en serio. Esto no lo puedo resolver yo: "
    "te estoy comunicando ahora mismo con un asistente humano de la farmacia "
    "para que revise tu caso personalmente. Se comunicará contigo por este "
    "mismo chat."
)


# ---------------------------------------------------------------------------
# G1-ext — Superlativos de precio sin respaldo de catálogo
# ---------------------------------------------------------------------------
# El agente afirma que algo "es el más económico", "el más barato" o "el
# genérico de X" cuando last_products está vacío: no hay datos del catálogo
# que respalden esa comparación. Veto con la misma plantilla de G1.
SUPERLATIVO_PRECIO = re.compile(
    r"\b(m[aá]s\s+econ[oó]mic[oa]|m[aá]s\s+barat[oa]|m[aá]s\s+accesible|"
    r"opci[oó]n\s+m[aá]s\s+barat[oa]|precio\s+m[aá]s\s+baj[oa]|"
    r"el\s+gen[eé]rico\s+de|gen[eé]rico\s+m[aá]s\s+econ[oó]mic[oa])\b",
    re.I,
)


def cita_superlativo_precio(texto: str) -> bool:
    """G1-ext: el texto del AGENTE usa un superlativo de precio sin respaldo."""
    return bool(texto) and bool(SUPERLATIVO_PRECIO.search(texto))


# ---------------------------------------------------------------------------
# G5 — Afirmación de composición/genérico sin respaldo de catálogo
# ---------------------------------------------------------------------------
# El agente afirma el principio activo, la composición o la equivalencia
# genérica de un medicamento cuando NO hay resultados de tool que lo
# respalden. Hallazgo del Laboratorio: Daflon con "principio activo ramiprilo"
# o Daflon con "el genérico más económico del...". Plantilla que no afirma
# nada y ofrece buscar en el catálogo.
AFIRMA_COMPOSICION = re.compile(
    r"\b(principio\s+activo|mismo\s+principio\s+activo|"
    r"es\s+el\s+gen[eé]rico\s+de|gen[eé]rico\s+equivalente|"
    r"equivalente\s+gen[eé]rico|ingrediente\s+activo|"
    r"composici[oó]n\s+\w|contiene\s+[a-záéíóúñ]{4,})\b",
    re.I,
)

TPL_SIN_COMPOSICION = (
    "No tengo información confirmada sobre la composición o equivalencia "
    "genérica de ese medicamento en este momento y no quiero darte datos "
    "incorrectos. Puedo buscarlo en el catálogo para darte las opciones "
    "reales. ¿Lo buscamos?"
)


def afirma_composicion(texto: str) -> bool:
    """G5: el texto del AGENTE afirma principio activo, composición o equivalencia genérica."""
    return bool(texto) and bool(AFIRMA_COMPOSICION.search(texto))


# ---------------------------------------------------------------------------
# G6 — Precio, stock o principio activo directo sin respaldo de catálogo
# ---------------------------------------------------------------------------
# El agente afirma un precio con cifra concreta, una cantidad de stock ("hay
# N unidades") o la frase directa "el principio activo es X" sin haber
# obtenido resultados de buscar_medicamento en el turno actual. Complementa
# G1 (que requiere que el cliente preguntara el precio) y G5 (composición más
# amplia): G6 cubre el caso donde el LLM inventa datos sin que el usuario
# haya preguntado explícitamente.
AFIRMA_DATO_CATALOGO = re.compile(
    r"\$\s*\d+(?:[.,]\d{1,2})?"                                  # $5 / $12.50 / $12,50
    r"|\bBs\.?\s*\d+"                                            # Bs 50 / Bs. 50
    r"|\d+\s*(?:d[oó]lares?|bol[íi]vares?)\b"                   # 50 bolívares / 5 dólares
    r"|\b(?:hay|tenemos|tengo|disponemos\s+de)\s+\d+\s+"
    r"(?:unidades?|cajas?|piezas?|tabletas?|comprimidos?|frascos?|ampollas?)\b"  # stock
    r"|\bel\s+principio\s+activo\s+es\s+\w+"                    # el principio activo es ramiprilo
    r"|\bsu\s+principio\s+activo\s+es\s+\w+",                   # su principio activo es X
    re.I,
)

# Cierre constante de G6: sustituye la alucinación de datos de producto por
# una respuesta que reconoce la limitación y propone buscar en el catálogo.
TPL_VERIFICACION_CATALOGO = (
    "No tengo información confirmada sobre ese medicamento en este momento "
    "y no quiero darte datos incorrectos. Para precio, disponibilidad o "
    "composición exacta, déjame buscarlo en el catálogo. "
    "¿Cuál es el medicamento que buscas?"
)


def afirma_dato_catalogo(texto: str) -> bool:
    """G6: el texto del AGENTE afirma precio con dígitos, cantidad de stock o principio activo directo."""
    return bool(texto) and bool(AFIRMA_DATO_CATALOGO.search(texto))


# ---------------------------------------------------------------------------
# G7 — Eco: el agente repite casi literalmente el mensaje del cliente
# ---------------------------------------------------------------------------
# El LLM a veces devuelve el turno del cliente como si fuera su respuesta
# ("Perfecto, quiero 2 cajas de losartan 50 mg.") en lugar de ejecutar la
# acción (buscar en el catálogo, agregar al carrito, confirmar) o pedir el
# dato que falta. Esta guarda detecta el eco por solapamiento de tokens
# normalizado y lo reemplaza por una confirmación útil.

_ECO_MIN_TOKENS = 4  # textos con menos tokens no se evalúan (saludos cortos)

TPL_NO_ECHO = (
    "Perfecto, ya lo estoy buscando. En un momento te muestro las opciones disponibles."
)


def _normalizar_tokens(texto: str) -> list[str]:
    """Minúsculas, sin acentos, sin puntuación → lista de tokens."""
    texto = texto.lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    texto = re.sub(r"[^\w\s]", " ", texto)
    return texto.split()


def es_echo(texto_agente: str, texto_cliente: str) -> bool:
    """G7: True si el texto del agente es casi idéntico al último mensaje del cliente.

    Normaliza ambos textos (minúsculas, sin acentos ni puntuación) y calcula
    solapamiento de tokens en ambas direcciones: si AMBAS coberturas superan
    el 70 % el agente está repitiendo al cliente en vez de actuar.
    """
    if not texto_agente or not texto_cliente:
        return False
    ta = _normalizar_tokens(texto_agente)
    tc = _normalizar_tokens(texto_cliente)
    if len(ta) < _ECO_MIN_TOKENS or len(tc) < _ECO_MIN_TOKENS:
        return False
    if ta == tc:
        return True
    set_a, set_c = set(ta), set(tc)
    inter = len(set_a & set_c)
    overlap_a = inter / len(set_a) if set_a else 0
    overlap_c = inter / len(set_c) if set_c else 0
    return overlap_a > 0.70 and overlap_c > 0.70


def pide_precio_sin_dato(texto: str) -> bool:
    """G1: el cliente pide un precio (la llamada del guardián decide si hay
    respaldo del catálogo)."""
    return bool(texto) and bool(PIDE_PRECIO.search(texto))


def intencion_fuera_kb(texto: str) -> bool:
    """G2: el turno del cliente trata políticas de negocio fuera del KB."""
    return bool(texto) and bool(FUERA_KB.search(texto))


def menciona_media(texto: str) -> bool:
    """G3: el mensaje del cliente habla de fotos/adjuntos."""
    return bool(texto) and bool(MEDIA_MENCION.search(texto))


def afirma_recibir_media(texto: str) -> bool:
    """G3: el texto del AGENTE afirma que recibió/leyó una imagen."""
    return bool(texto) and bool(CLAIM_RECIBIO_MEDIA.search(texto))


def acusacion_fraude(texto: str) -> bool:
    """G4: acusación de fraude/robo dirigida al negocio."""
    return bool(texto) and bool(ACUSACION_FRAUDE.search(texto))


# ---------------------------------------------------------------------------
# G8 — Placeholder sin ejecutar: el agente escribe la plantilla en vez del dato
# ---------------------------------------------------------------------------
# El LLM puede "imitar" el formato de una tool-call escribiendo literalmente
# '[inserta información del producto desde buscar_medicamento]' en su respuesta
# en vez de LLAMAR la herramienta. El cliente recibe el esqueleto de una
# plantilla interna — fallo de protocolo grave detectado en QA 'Errores y
# modismos'. Solo se activa cuando el contenido del corchete parece instrucción
# (verbo infinitivo en español o nombre de herramienta); los corchetes
# legítimos (unidades, referencias) no disparan la guarda.
_TPL_BRACKET = re.compile(r"\[([^\]]{3,})\]")

_VERBOS_INSTRUCCION = re.compile(
    r"^(inserta|agrega|completa|coloca|escribe|pon|incluye|a[ñn]ade|describe|"
    r"muestra|lista|copia|usa|utiliza|indica|especifica)\b",
    re.I,
)

_NOMBRES_HERRAMIENTA = re.compile(
    r"\b(buscar_medicamento|agregar_al_carrito|ver_carrito|finalizar_pedido|"
    r"update_ficha|propose_slots|book_session|reschedule_session|route_out|"
    r"handoff|sugerir_generico)\b",
    re.I,
)

TPL_BUSQUEDA_HONESTA = (
    "Tuve un problema al completar la búsqueda y no quiero darte información "
    "incompleta. ¿Me repites el nombre del medicamento y lo busco ahora mismo?"
)


def tiene_placeholder(texto: str) -> bool:
    """G8: True si el texto del agente contiene un placeholder de instrucción entre corchetes.

    Activa solo cuando el contenido entre corchetes empieza con un verbo
    infinitivo de instrucción en español o contiene un nombre de herramienta.
    Cubre explícitamente '[inserta...' (caso QA 'Errores y modismos').
    """
    if not texto:
        return False
    if re.search(r"\[inserta\b", texto, re.I):
        return True
    for m in _TPL_BRACKET.finditer(texto):
        contenido = m.group(1).strip()
        if _VERBOS_INSTRUCCION.match(contenido) or _NOMBRES_HERRAMIENTA.search(contenido):
            return True
    return False
