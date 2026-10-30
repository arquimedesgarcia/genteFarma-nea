"""Conftest de los tests del agente NEA (F14).

`tests/` no existía en la rama `desarrollo`: se crea con las regresiones de F14
(casos reales del cliente + bordes de cada fix). El árbol del agente se importa
desde la raíz del repo (no hay paquete instalado) y el registro de alias se
limpia entre tests para que ninguno dependa del orden de ejecución.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))


@pytest.fixture(autouse=True)
def _alias_limpio():
    """Cada test arranca sin alias registrados (la semilla real vive en la DB)."""
    from app import aliases

    aliases.limpiar()
    yield
    aliases.limpiar()
