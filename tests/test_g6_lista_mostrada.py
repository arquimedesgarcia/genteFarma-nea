"""Batería: G6 no debe vetar cuando los importes vienen de la lista que el cliente YA vio.

Origen: prueba en vivo con tráfico real (provider 05, 2026-11-07). A "Este", "De ese",
"Si tienen disponibilidad." y "Y tegretol jarabe al 2%" el agente contestó la plantilla
"No tengo información confirmada sobre ese medicamento en este momento… y ¿cuál es el
medicamento que buscas?", que no venía a cuento: el turno no busca nada (last_products
vacío) pero el agente SÍ tenía respaldo, la lista del turno anterior (last_options).

Además, cuando hay lista mostrada la pregunta correcta es POR LA OPCIÓN, no por el nombre.
"""
import sys
import types

sys.path.insert(0, "/Users/robertosomoza/HermesProyectos/nea-agent")

from app import guards, turn  # noqa: E402


class _R:
    def __init__(self, opciones):
        self.last_options = opciones
        self.last_products = []


LISTA = [
    {"producto": "NITROFURANTOINA 100MG CAPS", "precio": 0.55, "precioBs": 495.00},
    {"producto": "MACRODANTINA 50MGX30TAB", "precio": 10.49, "precioBs": 9415.18},
]


def _check(nombre, cond):
    print(f"  {'OK ' if cond else 'MAL'} {nombre}")
    return cond


def main():
    ok = total = 0

    def t(nombre, cond):
        nonlocal ok, total
        total += 1
        ok += 1 if _check(nombre, cond) else 0

    print("── importes respaldados por la lista mostrada ──")
    r = _R(LISTA)
    t("una sola cifra en USD", turn._montos_respaldados("Sí, hay disponibilidad. Cuesta $0,55", r))
    t("USD + Bs con miles", turn._montos_respaldados("Está en $10,49 | Bs 9.415,18", r))
    t("varias cifras reales", turn._montos_respaldados("$0,55 | Bs 495,00 o $10,49", r))
    t("cifra inventada → NO respaldada", not turn._montos_respaldados("Cuesta $8,99", r))
    t("mezcla real e inventada → NO", not turn._montos_respaldados("$0,55 y otra en $8,99", r))
    t("sin cifras → NO respaldada", not turn._montos_respaldados("Sí, hay disponibilidad.", r))

    print("── sin lista mostrada siempre es NO ──")
    t("sin last_options", not turn._montos_respaldados("cuesta $0,55", _R([])))

    print("── parser de importes ──")
    t("7,02 → 7.02", abs((turn._a_float("7,02") or 0) - 7.02) < 1e-9)
    t("6.290,78 → 6290.78", abs((turn._a_float("6.290,78") or 0) - 6290.78) < 1e-9)
    t("2.629 → 2629", abs((turn._a_float("2.629") or 0) - 2629.0) < 1e-9)
    t("basura → None", turn._a_float("") is None)

    print("── la plantilla cambia si hay lista ──")
    t("existe la plantilla con lista", hasattr(guards, "TPL_VERIFICACION_CATALOGO_CON_LISTA"))
    t("pregunta por la opción", "opci" in guards.TPL_VERIFICACION_CATALOGO_CON_LISTA.lower())
    t("no vuelve a pedir el nombre", "cuál es el medicamento" not in guards.TPL_VERIFICACION_CATALOGO_CON_LISTA.lower())
    t("la original sigue pidiendo el nombre", "cuál es el medicamento" in guards.TPL_VERIFICACION_CATALOGO.lower())

    print(f"\n  {ok}/{total} OK")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
