"""Normalización del texto al dialecto de WhatsApp.

WhatsApp NO interpreta Markdown: solo entiende `*negrita*`, `_cursiva_`,
`~tachado~` y ``` ```monoespaciado``` ```. El LLM, en cambio, escribe Markdown
(`**negrita**`), y el cliente recibía los asteriscos literales:

    💊 1. **POLIFIX POLVO FIJADOR PARA PROTESIS DENTALES X 30 GR**

en vez del nombre en negrita. Todo lo que sale hacia el cliente pasa por
`a_formato_whatsapp()` (turn.py::_send) para que el dialecto sea siempre el de
WhatsApp, venga del LLM o de un formateador determinista.
"""

from __future__ import annotations

import re

# ***x*** (negrita + cursiva) ANTES que **x**: si no, el par interior se come uno
# de los asteriscos y queda un resto suelto.
_RE_NEGRITA_CURSIVA = re.compile(r"\*\*\*(?=\S)(.+?)(?<=\S)\*\*\*", re.S)
# **x** → *x*  (negrita Markdown → negrita WhatsApp). \S en los bordes evita
# comerse listas con asteriscos separados por espacios.
_RE_NEGRITA = re.compile(r"\*\*(?=\S)(.+?)(?<=\S)\*\*", re.S)
# __x y__ → *x y*: solo cuando el contenido lleva un espacio dentro, que es el
# caso real (nombres de producto). Convertir cualquier __x__ destrozaría
# identificadores tipo __init__ o __name__ de un texto técnico.
_RE_NEGRITA_BAJA = re.compile(r"__(?=\S)([^_\n]*\s[^_\n]*?)(?<=\S)__")
# "__" que sobreviven (negrita de una sola palabra, o sin pareja): se eliminan.
# WhatsApp no tiene sintaxis con guion bajo doble, así que se verían literales.
_RE_DOBLE_BAJA = re.compile(r"__")
# ~~x~~ → ~x~  (tachado)
_RE_TACHADO = re.compile(r"~~(?=\S)(.+?)(?<=\S)~~", re.S)
# Encabezados "# Título" → "Título" (WhatsApp mostraría la almohadilla)
_RE_ENCABEZADO = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+", re.M)
# `código` en línea → código (WhatsApp solo entiende ``` para monoespaciado)
_RE_CODIGO = re.compile(r"`([^`\n]+)`")
# [texto](url) → texto: url
_RE_ENLACE = re.compile(r"\[([^\]\n]+)\]\((https?://[^)\s]+)\)")
# Restos de "**" sin pareja: se eliminan. Un asterisco suelto se vería literal
# en WhatsApp, que exige pareja para dar formato.
_RE_ASTERISCOS_DOBLES = re.compile(r"\*\*")


def a_formato_whatsapp(texto: str) -> str:
    """Convierte marcas de Markdown a lo que WhatsApp sí renderiza.

    Es idempotente: aplicarla dos veces da el mismo resultado. No toca el
    formato canónico de las listas (`💊 1. NOMBRE`), que no lleva marcas.
    """
    if not texto:
        return texto

    t = texto
    t = _RE_NEGRITA_CURSIVA.sub(r"*_\1_*", t)
    t = _RE_NEGRITA.sub(r"*\1*", t)
    t = _RE_NEGRITA_BAJA.sub(r"*\1*", t)
    t = _RE_DOBLE_BAJA.sub("", t)
    t = _RE_TACHADO.sub(r"~\1~", t)
    t = _RE_ENCABEZADO.sub("", t)
    t = _RE_CODIGO.sub(r"\1", t)
    t = _RE_ENLACE.sub(r"\1: \2", t)
    t = _RE_ASTERISCOS_DOBLES.sub("", t)
    return t
