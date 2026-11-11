"""Contratos tipados del caso de uso de búsqueda de catálogo (UC-01).

Formaliza, de forma **aditiva**, los resultados que hoy devuelve el handler real
`app.tools.ToolRuntime._buscar_medicamento` como `dict {ok, ...}` heterogéneos
(ver `docs/architecture/TO-BE.md` §4 y `docs/architecture/USE-CASES.md` UC-01).

No reimplementa la búsqueda: solo **describe** su salida. `CatalogSearchResult.raw`
conserva el dict original intacto y `to_tool_dict()` lo devuelve sin tocar, de modo
que cualquier consumidor que hoy espere el dict (p. ej. el LLM vía `instrucciones`)
siga recibiendo exactamente la misma serialización.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CatalogSearchStatus(str, Enum):
    """Resultados tipados de UC-01, mapeados contra el handler AS-IS.

    Es un subconjunto de los resultados comunes del TO-BE §4: declara solo los que
    el handler real emite hoy. `AMBIGUO` queda **reservado**: el handler actual no
    produce un dict distinto para "varias opciones / forma no resuelta" (esa
    ambigüedad se presenta hoy como `PARCIAL` vía `aviso_forma`).
    """

    ENCONTRADO = "encontrado"
    PARCIAL = "parcial"
    NO_ENCONTRADO = "no_encontrado"
    NO_AUTORIZADO = "no_autorizado"
    NO_CONSULTA = "no_consulta"
    PROVEEDOR_NO_DISPONIBLE = "proveedor_no_disponible"
    ERROR = "error"  # error no reconocido del handler — no se asume que sea NO_CONSULTA
    AMBIGUO = "ambiguo"  # reservado — sin fuente distinta en el AS-IS actual


# Errores internos del handler que significan "el término NO es una consulta de
# medicamento buscable" (no se tocó el catálogo). Se agrupan en NO_CONSULTA.
_ERRORES_NO_CONSULTA = frozenset(
    {"nombre_vacio", "solo_sal", "sin_medicamento", "solo_saludo", "no_medicamento"}
)

# Errores con mapeo directo a un estado tipado.
_ERRORES_DIRECTOS: dict[str, CatalogSearchStatus] = {
    "sin_resultados": CatalogSearchStatus.NO_ENCONTRADO,
    "no_autorizado_por_comprension": CatalogSearchStatus.NO_AUTORIZADO,
    "crm_error": CatalogSearchStatus.PROVEEDOR_NO_DISPONIBLE,
}


class ApplicationError(Exception):
    """Error de la capa de aplicación (base)."""


class ProveedorNoDisponibleError(ApplicationError):
    """Una dependencia externa (CRM/LLM) no está disponible o agotó su tiempo.

    El adaptador por defecto (`ToolRuntimeCatalogAdapter`) NO la lanza —delega en
    `ToolRuntime.execute`, que ya traduce `CrmError` a `{ok:False,error:"crm_error"}`—,
    pero un adaptador que envuelva infraestructura cruda puede lanzarla; el caso de
    uso la normaliza a `PROVEEDOR_NO_DISPONIBLE` sin filtrar la excepción de infra.
    """


@dataclass(frozen=True)
class CatalogSearchRequest:
    """Entrada mínima del caso de uso: el término tal como se pidió buscar."""

    termino: str


@dataclass(frozen=True)
class CatalogSearchResult:
    """Resultado tipado de una búsqueda de catálogo.

    `raw` es el dict exacto devuelto por el handler/adaptador; `to_tool_dict()` lo
    devuelve sin modificar para preservar la serialización observable.
    """

    status: CatalogSearchStatus
    termino: str
    productos: list[dict[str, Any]] = field(default_factory=list)
    detalle: str | None = None
    aviso_forma: str | None = None
    por_principio_activo: bool = False
    raw: dict[str, Any] = field(default_factory=dict)

    def to_tool_dict(self) -> dict[str, Any]:
        """Serialización observable original (identidad), para consumidores legados."""
        return self.raw


def mapear_resultado(
    raw: dict[str, Any], *, aviso_forma: str = "", termino: str = ""
) -> CatalogSearchResult:
    """Traduce el dict del handler a un `CatalogSearchResult` tipado (función pura).

    `aviso_forma` se pasa aparte porque el dict de éxito no lo incluye: el handler lo
    funde en `instrucciones` y lo deja en el flag `runtime.aviso_forma`.
    """
    raw = raw or {}
    productos = list(raw.get("products") or [])
    detalle = raw.get("detalle")
    aviso = (aviso_forma or "").strip()

    if raw.get("ok"):
        if raw.get("principio_activo"):
            # Marca exacta ausente; se ofrecen alternativas por principio activo.
            return CatalogSearchResult(
                status=CatalogSearchStatus.PARCIAL,
                termino=termino,
                productos=productos,
                detalle=detalle,
                aviso_forma=aviso or None,
                por_principio_activo=True,
                raw=raw,
            )
        if aviso:
            # Hay producto pero no en la forma pedida; se muestran alternativas.
            return CatalogSearchResult(
                status=CatalogSearchStatus.PARCIAL,
                termino=termino,
                productos=productos,
                detalle=detalle,
                aviso_forma=aviso,
                raw=raw,
            )
        return CatalogSearchResult(
            status=CatalogSearchStatus.ENCONTRADO,
            termino=termino,
            productos=productos,
            detalle=detalle,
            raw=raw,
        )

    error = raw.get("error")
    if error in _ERRORES_DIRECTOS:
        status = _ERRORES_DIRECTOS[error]
    elif error in _ERRORES_NO_CONSULTA:
        status = CatalogSearchStatus.NO_CONSULTA
    else:
        # Un error no catalogado NO se asume como NO_CONSULTA: podría ser un fallo real
        # que quedaría enmascarado como "el cliente no pidió un medicamento". Se tipa
        # como ERROR explícito para que el consumidor lo trate como anomalía.
        status = CatalogSearchStatus.ERROR
    return CatalogSearchResult(
        status=status,
        termino=termino,
        productos=productos,
        detalle=detalle,
        aviso_forma=aviso or None,
        raw=raw,
    )
