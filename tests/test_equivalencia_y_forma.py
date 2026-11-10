"""Prueba en vivo con tráfico real (Ospino → FarmaHogar, 2026-11-06).

Dos incoherencias que salieron en la conversación real y su guarda:

1. `Vivacina es sertralina, y sí la tengo` + lista de SERTRALINA. El mapeo marca →
   principio activo lo adivina el LLM; dos turnos antes, con la misma palabra, había
   contestado DOXICICLINA. No se puede afirmar.

2. `⚠️ No tengo BUCAL. De PINVEX hay esto:` y `⚠️ No tengo SOLUNOVAL. De BUCAL hay esto:`
   La forma farmacéutica no es un producto que se tenga o no.
"""
from __future__ import annotations

from typing import Any

from app import turn


class _Runtime:
    principio_inferido: tuple[str, str] | None = None


def _rt(marca: str | None = None, principio: str | None = None) -> Any:
    r = _Runtime()
    r.principio_inferido = (marca, principio) if marca and principio else None
    return r


# ── 1) equivalencia inventada ────────────────────────────────────────────────

def test_quita_la_afirmacion_y_conserva_el_ofrecimiento():
    texto = (
        "Vivacina es sertralina, y sí la tengo. Estas son las opciones:\n\n"
        "SERTRALINA\n"
        "💊 1. SERTRALINA 50 MG X 10 COMP GENVEN\n"
        "   $3,71  |  Bs 3.324,61\n"
    )
    salida = turn._sin_equivalencia_inventada(texto, _rt("vivacina", "sertralina"))
    assert "Vivacina es sertralina" not in salida
    assert "No tengo «VIVACINA»" in salida
    assert "SERTRALINA 50 MG X 10 COMP GENVEN" in salida, "la lista real debe sobrevivir"


def test_no_toca_la_respuesta_cuando_no_hay_mapeo_inferido():
    texto = "Vivacina es sertralina, y sí la tengo."
    assert turn._sin_equivalencia_inventada(texto, _rt()) == texto


def test_no_toca_un_ofrecimiento_condicional():
    # "si buscas sertralina" NO afirma que vivacina lo sea
    texto = "No tengo VIVACINA. Si buscas sertralina, tengo:\n\n💊 1. SERTRALINA 50 MG"
    assert turn._sin_equivalencia_inventada(texto, _rt("vivacina", "sertralina")) == texto


def test_no_toca_una_respuesta_sin_relacion():
    texto = "¡Hola! Soy Robi. ¿Qué medicamento estás buscando hoy?"
    assert turn._sin_equivalencia_inventada(texto, _rt("vivacina", "sertralina")) == texto


# ── 2) la forma no es un producto ─────────────────────────────────────────────

def test_la_forma_no_genera_aviso():
    assert turn._aviso_no_lo_tengo("pinvex bucal", "bucal") == ""


def test_marca_ausente_con_resto_que_es_forma_no_dice_de_que_hay():
    salida = turn._aviso_no_lo_tengo("solunoval bucal", "solunoval")
    assert salida == "⚠️ No tengo SOLUNOVAL."


def test_la_marca_ausente_sigue_avisando():
    assert turn._aviso_no_lo_tengo("sensodyne", "sensodyne") == "⚠️ No tengo SENSODYNE."
    assert "FIN-AL-GRIP" in turn._aviso_no_lo_tengo("fin-al-grip", "fin-al-grip")


def test_la_marca_con_resto_util_conserva_el_de_hay_esto():
    salida = turn._aviso_no_lo_tengo("amor nitrofurantoina", "amor")
    assert salida == "⚠️ No tengo AMOR. De NITROFURANTOINA hay esto:"
