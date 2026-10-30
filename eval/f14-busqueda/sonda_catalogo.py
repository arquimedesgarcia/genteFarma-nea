"""Sonda contra el catálogo REAL del CRM (provider demo del entorno de QA).

Corre DENTRO del contenedor nea (donde viven las deps) y mide, término a
término: cuántos productos devuelve el catálogo y cuántos sobreviven al filtro
de relevancia. Compara los términos VIEJOS (antes de F14) con los NUEVOS.
"""
from __future__ import annotations

import asyncio
import json
import os

from app.aliases import cargar_desde_store, limpiar, reescribir
from app.crm import CrmClient
from app.relevancia import filtrar_relevantes

PROVEEDOR = os.environ.get("PROVEEDOR", "demo")

TERMINOS = [
    # (etiqueta, término)
    ("C1 viejo (bug)", "amor nitrofurantoina 50mg vitamina"),
    ("C1 nuevo A", "nitrofurantoina 50mg"),
    ("C1 nuevo B", "vitamina c"),
    ("C1 vitamina sin letra", "vitamina"),
    ("C2 vivacina", "vivacina"),
    ("C4 solunoval (typo)", "solunoval"),
    ("C4 solunovar (canónico)", "solunovar"),
    ("C4 pinvex", "pinvex"),
    ("typo omeprasol", "omeprasol"),
    ("typo fexofenasina", "fexofenasina"),
    ("canónico fexofenadina", "fexofenadina"),
]


async def main() -> None:
    crm = CrmClient(os.environ["CRM_BASE_URL"], os.environ["CRM_BOT_API_KEY"])
    salida: list[dict] = []
    try:
        for etiqueta, termino in TERMINOS:
            try:
                data = await crm.get_products(PROVEEDOR, q=termino, limit=20)
            except Exception as exc:  # el CRM caído no debe romper la sonda
                salida.append({"etiqueta": etiqueta, "termino": termino,
                               "error": str(exc)})
                continue
            productos = data.get("products") or []
            filtrados = filtrar_relevantes(termino, productos)
            salida.append({
                "etiqueta": etiqueta,
                "termino": termino,
                "catalogo": len(productos),
                "relevantes": len(filtrados),
                "nombres_relevantes": [
                    str(p.get("nombre") or p.get("title") or "")[:60]
                    for p in filtrados[:6]
                ],
                "descartados": [
                    str(p.get("nombre") or p.get("title") or "")[:60]
                    for p in productos
                    if p not in filtrados
                ][:6],
            })
        # Alias: reescribir y volver a medir (simula lo que hace la herramienta).
        limpiar()
        n = await cargar_desde_store(_StoreAlias())
        print(f"alias cargados: {n}")
        for etiqueta, termino in [("C4 solunoval bucal", "solunoval solución bucal"),
                                  ("alfajor? no: fexofenasina", "fexofenasina")]:
            nuevo, aplicado = reescribir(termino)
            if not aplicado:
                salida.append({"etiqueta": etiqueta + " (sin alias)", "termino": termino,
                               "detalle": "el módulo no lo reconoció"})
                continue
            data = await crm.get_products(PROVEEDOR, q=nuevo, limit=20)
            productos = data.get("products") or []
            filtrados = filtrar_relevantes(nuevo, productos, permitir_typo=False)
            salida.append({
                "etiqueta": etiqueta + " (con alias)",
                "termino": f"{termino} → {nuevo}",
                "catalogo": len(productos),
                "relevantes": len(filtrados),
                "nombres_relevantes": [
                    str(p.get("nombre") or p.get("title") or "")[:60]
                    for p in filtrados[:6]
                ],
                "descartados": [],
            })
    finally:
        await crm.aclose()
    print(json.dumps(salida, ensure_ascii=False, indent=1))


class _StoreAlias:
    """Lee la tabla med_aliases de la DB del contenedor (como en el arranque)."""

    async def list_med_aliases(self):
        import asyncpg

        conn = await asyncpg.connect(os.environ["DATABASE_URL"])
        try:
            filas = await conn.fetch("SELECT alias, canonico FROM med_aliases")
            return [dict(f) for f in filas]
        finally:
            await conn.close()


if __name__ == "__main__":
    asyncio.run(main())
