"""Adaptador compatible: expone `ToolRuntime` como `CatalogSearchPort`.

**No duplica** `ToolRuntime` ni ninguna dependencia: delega la búsqueda en
`ToolRuntime.execute("buscar_medicamento", ...)`, el mismo punto que usa hoy la ruta
caliente (`turn.py`). Por eso hereda, sin cambios, el manejo de `CrmError` que
`execute` traduce a `{ok: False, error: "crm_error"}` (`app/tools.py:2465`).
"""
from __future__ import annotations

from typing import Any


class ToolRuntimeCatalogAdapter:
    """Envuelve un `ToolRuntime` (del turno en curso) como puerto de búsqueda."""

    def __init__(self, runtime: Any) -> None:
        self._runtime = runtime

    async def buscar(self, termino: str) -> dict[str, Any]:
        return await self._runtime.execute("buscar_medicamento", {"nombre": termino})

    @property
    def aviso_forma(self) -> str:
        return getattr(self._runtime, "aviso_forma", "") or ""
