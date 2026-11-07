"""Batería: la respuesta tiene que ser de la FAMILIA que se pidió.

Origen: prueba en vivo con tráfico real (provider 05, FarmaHogar, 2026-11-07).

    "Buenas tardes por favor el precio de solunoval solución bucal"
    → BEDEX SOL TOPICA BUCAL · MIEL DE BORAX TOPICO BUCAL · FLODONT · TANTUM SOL. BUCAL

'solunoval' no existe en ese catálogo (0 resultados buscándolo solo: 9.991 productos),
pero como el buscador usa OR entre tokens, el token 'solución bucal' sí encontró y el
cliente recibió cuatro marcas de otra familia como si fueran lo que pidió.

La regla del negocio: cuando la respuesta no es precisa es mejor no responder con
productos que no sean coherentes.
"""
import sys

sys.path.insert(0, "/Users/robertosomoza/HermesProyectos/nea-agent")

from app import tools  # noqa: E402


def _p(nombre):
    return {"nombre": nombre}


CASOS = [
    # ── el nombre no existe: NO se contesta con la forma ──────────────────
    (
        "solunoval solución bucal",
        [
            "BEDEX SOL TOPICA BUCAL X 120ML",
            "MIEL DE BORAX TOPICO BUCAL X 20 ML",
            "FLODONT ENJUAGUE BUCAL X 180ML",
            "TANTUM SOL. BUCAL 0.15%",
        ],
        [],
        "nombre inexistente: no se ofrece la forma",
    ),
    (
        "vivacina 100 mg",
        ["VITAMINA C 500MG X 10 TAB", "VITAMINA E 400UI X 30 CAPS"],
        [],
        "vivacina ≠ vitamina",
    ),
    # ── el nombre existe: se queda lo suyo y se va lo ajeno ───────────────
    (
        "pinvex solución bucal",
        ["PINVEX 5G-1G/100 ML (E) COFASA", "BEDEX SOL TOPICA BUCAL X 120ML"],
        ["PINVEX 5G-1G/100 ML (E) COFASA"],
        "se queda PINVEX, se va BEDEX",
    ),
    (
        "nitrofurantoina 100 mg",
        ["NITROFURANTOINA  100MG CAPSULAS X 10 LAPROFF", "MACRODANTINA 50MGX30TAB FARMA"],
        ["NITROFURANTOINA  100MG CAPSULAS X 10 LAPROFF"],
        "macrodantina no es nitrofurantoina por nombre",
    ),
    (
        "metronidazol ovulos",
        ["METRONIDAZOL 500MG X 10OVU ALESS", "OVUMET 500MG X 10OVU"],
        ["METRONIDAZOL 500MG X 10OVU ALESS"],
        "marca distinta no entra por nombre",
    ),
    # ── typos reales: NO se pueden perder ────────────────────────────────
    (
        "omeprasol 20 mg",
        ["OMEPRAZOL 20MG X 10 CAPS GENERICO"],
        ["OMEPRAZOL 20MG X 10 CAPS GENERICO"],
        "typo largo omeprasol → omeprazol",
    ),
    (
        "atamle 40 mg",
        ["ATAMEL 40MG X 10 TAB"],
        ["ATAMEL 40MG X 10 TAB"],
        "typo corto atamle → atamel",
    ),
    (
        "acido acetalicio 100 mg",
        ["ACIDO ACETILSALICILICO 100MG X 10 TAB"],
        ["ACIDO ACETILSALICILICO 100MG X 10 TAB"],
        "typo acetalicio → acetilsalicilico",
    ),
    (
        "losartan potasico 50 mg",
        ["LOSARTAN POTASICO 50MG X 30 TAB"],
        ["LOSARTAN POTASICO 50MG X 30 TAB"],
        "sal del compuesto",
    ),
    # ── pedidos sin nombre (categoría / forma): no se vacía la lista ─────
    (
        "crema para hongos",
        ["CLOTRIMAZOL CREMA 1% X 20GR", "MICONAZOL CREMA 2%"],
        ["CLOTRIMAZOL CREMA 1% X 20GR", "MICONAZOL CREMA 2%"],
        "categoría + enfermedad + forma: no hay token de nombre",
    ),
    (
        "jarabe para la tos",
        ["BROXOL JARABE X 120ML", "TUKOL JARABE X 120ML"],
        ["BROXOL JARABE X 120ML", "TUKOL JARABE X 120ML"],
        "solo forma + síntoma",
    ),
]


def main():
    ok = 0
    for termino, devueltos, esperados, nota in CASOS:
        got = tools._solo_de_la_familia_pedida(termino, [_p(n) for n in devueltos])
        nombres = [g["nombre"] for g in got]
        bien = nombres == esperados
        ok += 1 if bien else 0
        print(f"  {'OK ' if bien else 'MAL'} {nota}")
        print(f"       pidió {termino!r} → {len(nombres)}/{len(devueltos)}")
        if not bien:
            print(f"       esperado {esperados}")
            print(f"       obtenido {nombres}")
    print(f"\n  {ok}/{len(CASOS)} OK")
    return 0 if ok == len(CASOS) else 1


if __name__ == "__main__":
    sys.exit(main())
