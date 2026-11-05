"""F15.1 — sonda determinista del PENDIENTE #1: la puerta es por TURNO, no por término.

Qué mide (sin modelo, sin catálogo real, sin llamadas):
  A) Turno autorizado por el BACKSTOP con `vivacina`: ¿pasan después los términos que el
     MODELO inventa (`vitamina`, `acabo`, `ustedes`)?
  B) Turno autorizado por la CAPA con `losartan`: ¿pasa un segundo término distinto?
  C) ¿Toda puerta al catálogo pasa por `_autorizar_busqueda`? (`sugerir_generico`)

Salida: una línea por caso con VEREDICTO (pasa/no pasa) y el conteo de consultas al CRM.
Código sin cambios: la sonda es de solo lectura sobre el árbol que se le pase.

Uso en el host:  PYTHONPATH=<repo> .venv-test/Scripts/python.exe eval/f15-frases-conversacion/probe_autorizacion_por_termino.py
Uso en el contenedor: PYTHONPATH=/app python eval/f15-frases-conversacion/probe_autorizacion_por_termino.py
"""

from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.environ.get("RAIZ", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from app.tools import ToolRuntime  # noqa: E402


class CrmFake:
    """Catálogo mínimo: registra CADA consulta que le llega."""

    def __init__(self):
        self.consultas: list[str] = []

    async def get_products(self, provider_id, q=None, limit=20):
        self.consultas.append(q or "")
        return {
            "products": [{"producto": "VITAMINA C 500 MG", "nombre": "VITAMINA C 500 MG",
                          "precio": 3.0, "precioBs": 2250.0, "productId": "p1",
                          "generico": "acido ascorbico"}],
            "provider": {"nombre": "QA", "paymeType": None, "hours": None},
        }


class StoreFake:
    def __init__(self):
        self.decisiones: list[dict] = []

    async def log_intent_decision(self, **kw):
        self.decisiones.append(kw)


class CtxFake:
    def __init__(self, crm, store):
        self.crm = crm
        self.store = store
        self.settings = SimpleNamespace(intent_layer=True)
        self.llm = object()


def runtime(**campos) -> ToolRuntime:
    rt = ToolRuntime.__new__(ToolRuntime)
    rt.intent_fuente = ""
    rt.intent_acto = ""
    rt.intent_motivo = ""
    rt.intent_confianza = None
    rt.intent_hay_consulta = None
    rt.intent_termino = None
    rt.intent_autorizado = None
    rt.texto_cliente = ""
    rt.last_product = None
    rt._provider_id_val = "demo"
    crm = CrmFake()
    store = StoreFake()
    if not hasattr(rt, "intent_terminos_autorizados"):
        rt.intent_terminos_autorizados = set()
    rt._ctx = CtxFake(crm, store)
    for k, v in campos.items():
        setattr(rt, k, v)

    async def registrar_decision_intencion(candidato=None):
        store.decisiones.append({"candidato": candidato})

    async def registrar_decision(candidato=None):
        return await registrar_decision_intencion(candidato)

    rt.registrar_decision_intencion = registrar_decision
    return rt


async def veredicto(rt: ToolRuntime, nombre: str) -> str:
    r = await rt._autorizar_busqueda(nombre)
    return "PASA" if r is None else f"NO PASA ({r.get('error')})"


async def main() -> int:
    fallos = 0
    print("== A) turno autorizado por el BACKSTOP (termino='vivacina') ==")
    rt = runtime(
        texto_cliente="tienen vivacina?",
        intent_fuente="capa",
        intent_acto="consulta_medicamento",
        intent_motivo="consulta por vivacina",
        intent_confianza=0.95,
        intent_hay_consulta=True,
        intent_termino="vivacina",
        intent_autorizado=True,
    )
    for termino, esperado in (("vivacina", "PASA"), ("vitamina", "NO PASA"),
                              ("acabo", "NO PASA"), ("ustedes", "NO PASA")):
        v = await veredicto(rt, termino)
        marca = "" if v.startswith(esperado) else "   <-- HUECO"
        if marca:
            fallos += 1
        print(f"   modelo busca '{termino}': {v}{marca}")

    print("== B) turno autorizado por la CAPA (termino='losartan') ==")
    rt = runtime(
        texto_cliente="tienes losartan 50 mg?",
        intent_fuente="llm",
        intent_acto="consulta_medicamento",
        intent_motivo="consulta legítima",
        intent_confianza=0.95,
        intent_hay_consulta=True,
        intent_termino="losartan",
        intent_autorizado=True,
    )
    for termino, esperado in (("losartan 50", "PASA"), ("vitamina", "NO PASA"),
                              ("acabo", "NO PASA")):
        v = await veredicto(rt, termino)
        marca = "" if v.startswith(esperado) else "   <-- HUECO"
        if marca:
            fallos += 1
        print(f"   modelo busca '{termino}': {v}{marca}")

    print("== C) otra puerta al catálogo: sugerir_generico ==")
    rt = runtime(texto_cliente="tienen vivacina?")  # nada autorizado en el turno
    r = await rt._sugerir_generico({"nombre": "vitamina"})
    consultas = rt._ctx.crm.consultas
    hueco = bool(consultas)
    if hueco:
        fallos += 1
    print(f"   sugerir_generico('vitamina') sin autorización → consultó el catálogo: "
          f"{consultas} {'<-- HUECO (no pasa por la puerta)' if hueco else ''}")
    print(f"   resultado ok={r.get('ok')}")

    print()
    print(f"HUECOS DETECTADOS: {fallos}")
    return 1 if fallos else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
