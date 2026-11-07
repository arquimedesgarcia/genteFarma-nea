"""Batería: la respuesta tiene que ser de la FAMILIA que se pidió.

Origen: prueba en vivo con tráfico real (provider 05, FarmaHogar, 2026-11-07).

    "Buenas tardes por favor el precio de solunoval solución bucal"
    → BEDEX SOL TOPICA BUCAL · MIEL DE BORAX TOPICO BUCAL · FLODONT · TANTUM SOL. BUCAL

'solunoval' no existe en ese catálogo (0 resultados buscándolo solo, sobre 9.991), pero el
buscador usa OR entre tokens: 'bucal' —que es una VÍA, no un nombre— matcheó cuatro marcas
de otra familia y el cliente las recibió como si fueran lo que pidió.

Dos agujeros, los dos en `app/relevancia.py`:

  a) `bucal`, `topico`, `oftalmica`, `vaginal`… no estaban en `_PRESENTACION_AUDIENCIA`,
     así que contaban como señal del fármaco.
  b) la regla de prefijo aceptaba tokens de 3 letras del producto (`len(t) >= 3`), así que
     "SOL" de TANTUM SOL. BUCAL validaba 'solunovar' por prefijo.

La regla del negocio: cuando la respuesta no es precisa es mejor no responder con
productos que no sean coherentes.
"""
import sys

sys.path.insert(0, "/Users/robertosomoza/HermesProyectos/nea-agent")

from app.relevancia import filtrar_relevantes, tokens_farmaco  # noqa: E402


def _p(nombre):
    return {"nombre": nombre}


CASOS = [
    # ── el nombre no existe: NO se contesta con la vía ni con la forma ────
    (
        "solunoval bucal",
        [
            "BEDEX SOL TOPICA BUCAL X 120ML",
            "TANTUM SOL. BUCAL 0.15%",
            "MIEL DE BORAX TOPICO BUCAL X 20 ML",
            "FLODONT ENJUAGUE BUCAL X 180ML",
        ],
        0,
        "nombre inexistente: la vía 'bucal' no valida",
    ),
    (
        "solunovar bucal",
        ["BEDEX SOL TOPICA BUCAL X 120ML", "TANTUM SOL. BUCAL 0.15%"],
        0,
        "el token de 3 letras 'SOL' no valida por prefijo",
    ),
    (
        "vivacina 100 mg",
        ["VITAMINA C 500MG X 10 TAB", "VITAMINA E 400UI X 30 CAPS"],
        0,
        "vivacina ≠ vitamina",
    ),
    (
        "dovilin jarabe adulto",
        ["BRONCOXOL JARABE ADULTO", "JARABE PARA LA TOS ADULTO"],
        0,
        "jarabe/adulto no validan (DOVILIN no existe)",
    ),
    # ── el nombre existe: se queda lo suyo y se va lo ajeno ───────────────
    (
        "pinvex bucal",
        ["PINVEX 5G-1G/100 ML (E) COFASA", "TANTUM SOL. BUCAL 0.15%"],
        1,
        "se queda PINVEX, se va TANTUM",
    ),
    (
        "nitrofurantoina 100 mg",
        ["NITROFURANTOINA  100MG CAPSULAS X 10 LAPROFF", "MACRODANTINA 50MGX30TAB FARMA"],
        1,
        "macrodantina no es nitrofurantoina por nombre",
    ),
    (
        "metronidazol ovulos",
        ["METRONIDAZOL 500MG X 10OVU ALESS", "OVUMET 500MG X 10OVU"],
        1,
        "marca distinta no entra por nombre",
    ),
    # ── typos reales: NO se pueden perder ────────────────────────────────
    ("omeprasol 20 mg", ["OMEPRAZOL 20MG X 10 CAPS GENERICO"], 1, "omeprasol → omeprazol"),
    ("atamle 40 mg", ["ATAMEL 40MG X 10 TAB"], 1, "atamle → atamel"),
    (
        "acido acetalicio 100 mg",
        ["ACIDO ACETILSALICILICO 100MG X 10 TAB"],
        1,
        "acetalicio → acetilsalicilico",
    ),
    # ── controles legítimos que ya funcionaban ───────────────────────────
    (
        "losartan potasico 50 mg",
        ["LOSARTAN POTASICO 50MG X 30 TAB", "LOSARTAN 50MG X 30 TAB"],
        1,
        "la sal del compuesto",
    ),
    ("sertralina 50 mg", ["SERTRALINA 50MG X 30 TAB"], 1, "principio directo"),
    ("buscapina amp", ["BUSCAPINA 20MG/ML AMP X 1"], 1, "marca + presentación"),
    ("enjuague bucal", ["FLODONT ENJUAGUE BUCAL X 180ML"], 1, "'enjuague' sí identifica"),
    ("agua de rosas", ["AGUA DE ROSAS X 250ML"], 1, "producto de dos palabras"),
    (
        "venta aceite oregano",
        ["ACEITE OREGANO X 30ML GOT NATURAL PREMIUM"],
        1,
        "'venta' ya no es término",
    ),
    (
        "amoxicilina acido clavulanico",
        ["AMOXICILINA+CLAVULANICO SUSP 400MG"],
        1,
        "compuesto con +",
    ),
    # ── pedidos sin nombre (forma / síntoma): no se vacía la lista ───────
    (
        "jarabe para la tos",
        ["BROXOL JARABE X 120ML", "TUKOL JARABE X 120ML"],
        2,
        "solo forma + síntoma",
    ),
]


def main():
    ok = 0
    for termino, devueltos, esperados, nota in CASOS:
        got = filtrar_relevantes(termino, [_p(n) for n in devueltos])
        bien = len(got) == esperados
        ok += 1 if bien else 0
        print(f"  {'OK ' if bien else 'MAL'} {termino!r:32} -> {len(got)}/{len(devueltos)}  ({nota})")
        if not bien:
            print(f"       esperado {esperados} · obtenido {[g['nombre'] for g in got]}")
    # la vía y la forma no son tokens de fármaco
    for termino in ("solunoval bucal", "solunoval solución bucal"):
        tokens = tokens_farmaco(termino)
        bien = tokens == ["solunoval"]
        ok += 1 if bien else 0
        print(f"  {'OK ' if bien else 'MAL'} tokens_farmaco({termino!r}) = {tokens}")
    total = len(CASOS) + 2
    print(f"\n  {ok}/{total} OK")
    return 0 if ok == total else 1


if __name__ == "__main__":
    sys.exit(main())
