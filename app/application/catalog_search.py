"""Caso de uso: buscar catálogo (UC-01).

Orquesta una búsqueda ya existente y traduce su salida a un contrato tipado. **No**
llama al LLM y **no** toma decisiones de autorización: la puerta única F15.1
(`tools._autorizar_busqueda`) vive dentro del motor que el puerto envuelve
([ADR-0002](../../docs/architecture/ADR/ADR-0002-llm-sin-autoridad.md),
[ADR-0003](../../docs/architecture/ADR/ADR-0003-puerta-unica-autorizacion.md)).

Es **aditivo**: hoy ningún componente de la ruta caliente lo invoca.
"""
from __future__ import annotations

from app.application.contracts import (
    CatalogSearchRequest,
    CatalogSearchResult,
    CatalogSearchStatus,
    ProveedorNoDisponibleError,
    mapear_resultado,
)
from app.application.ports import CatalogSearchPort


class BuscarCatalogoUseCase:
    """Ejecuta UC-01 contra un `CatalogSearchPort` y devuelve un resultado tipado."""

    def __init__(self, port: CatalogSearchPort) -> None:
        self._port = port

    async def ejecutar(self, request: CatalogSearchRequest) -> CatalogSearchResult:
        try:
            raw = await self._port.buscar(request.termino)
        except ProveedorNoDisponibleError as exc:
            # Un adaptador sobre infraestructura cruda puede señalar la caída así; se
            # normaliza a un resultado tipado sin filtrar la excepción de infra.
            detalle = str(exc) or None
            return CatalogSearchResult(
                status=CatalogSearchStatus.PROVEEDOR_NO_DISPONIBLE,
                termino=request.termino,
                detalle=detalle,
                raw={"ok": False, "error": "crm_error", "detalle": detalle},
            )
        # `asyncio.CancelledError` NO se captura: una cancelación/timeout del turno debe
        # propagarse tal cual (no convertir una cancelación en un resultado de negocio).
        aviso = getattr(self._port, "aviso_forma", "") or ""
        return mapear_resultado(raw, aviso_forma=aviso, termino=request.termino)
