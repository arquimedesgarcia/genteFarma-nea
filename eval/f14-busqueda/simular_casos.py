"""F14 — simulación DETERMINISTA de los 4 casos reales (sin LLM).

Ejecuta el código real de extracción y relevancia sobre los textos que el
cliente mandó por WhatsApp y reporta, en JSON, qué hacía el árbol ANTES y qué
hace AHORA. No hay modelo en el camino: todo es función pura, así que el
resultado es reproducible y auditable.

Uso (desde cualquier árbol del repo):

    python eval/f14-busqueda/simular_casos.py --root . --out salida.json

`--root` permite apuntar al árbol PREVIO (copia de `git archive HEAD`) y al
actual, y comparar con `diff`. Los imports que no existan en el árbol previo
(p. ej. `app.aliases`) se reportan como "no existe", no rompen la simulación.

La semilla de alias NO se duplica aquí: se lee del SQL real
(`migrations/012_med_aliases.sql`), así la simulación prueba exactamente lo que
cargará el agente en el arranque.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# --------------------------------------------------------------------- casos ---

# Textos REALES del cliente (los 4 del diagnóstico F14).
CASO_1 = "Buenas tardes!! Mi amor que precio tiene la nitrofurantoina de 50mg y la vitamina C"
CASO_2 = "vivacina"
CASO_3 = "Precio de la macrodantina?? Voy a querer una vitamina C de la opción 9"
CASO_4 = "buenas tardes precio de solunoval solución bucal y pinvex solución bucal"

# Productos del catálogo que aparecen en el diagnóstico (nombres reales medidos).
CATALOGO_C1 = [
    {"nombre": "TE AMO PRESERV. 3PCS"},
    {"nombre": "VITAMINA K 10 MG X 30 TAB"},
    {"nombre": "VITAMINA C 500 MG X 10 TAB"},
    {"nombre": "NITROFURANTOINA 100 MG X 20 CAP"},
]
CATALOGO_C2 = [
    {"nombre": "VITAMINA K 10 MG X 30 TAB"},
    {"nombre": "VITAMINA C 500 MG X 10 TAB"},
    {"nombre": "VITAMINAS B12 COMPLEJO X 30 CAP"},
]
CATALOGO_C4 = [
    {"nombre": "SOLUNOVAR SOLUCION BUCAL X 1 FCO"},
    {"nombre": "PINVEX SOLUCION BUCAL X 1 FCO"},
]

# Typos REALES que el proyecto ya daba por buenos: no pueden romperse.
TYPO_OK = [
    ("omeprasol", "OMEPRAZOL 20 MG X 30 CAP"),
    ("diclofencao", "DICLOFENACO 50 MG X 20 TAB"),
    ("amoxicilna", "AMOXICILINA 500 MG X 21 CAP"),
    ("solunoval", "SOLUNOVAR SOLUCION BUCAL X 1 FCO"),
    ("lorsatan", "LOSARTAN 50 MG X 30 TAB"),
    ("fexofenasina", "FEXOFENADINA 120 MG X 10 TAB"),
    ("azitromisina", "AZITROMICINA 500 MG X 3 TAB"),
    ("metmorfina", "METFORMINA 850 MG X 30 TAB"),
    ("clonacepan", "CLONAZEPAM 2 MG X 30 TAB"),
    ("shampo dreene", "SHAMPU DRENE X 1 FCO"),
    ("acetaminofen 650 mg", "ACETAMINOFEN 650 MG X 10 TAB"),
]

# Falsos positivos históricos: NUNCA pueden volver a matchear.
FALSO_POSITIVO = [
    ("hasta", "PASTA PRIMOR PLUMA"),
    ("todo", "DESODORANTE DOVE"),
    ("tarda delivery", "VENDA ELASTICA"),
    ("manana hora", "COMPOTA GERANIA"),
    ("amor", "TE AMO PRESERV. 3PCS"),
]

# Matriz de decisión del guard de typo (C2): qué pares tienen "parentesco" y
# qué pares son salto de categoría. Es la evidencia del reporte.
MATRIZ = {
    "typos_reales": [
        ("omeprasol", "omeprazol"), ("diclofencao", "diclofenaco"),
        ("amoxicilna", "amoxicilina"), ("solunoval", "solunovar"),
        ("lorsatan", "losartan"), ("fexofenasina", "fexofenadina"),
        ("azitromisina", "azitromicina"), ("metmorfina", "metformina"),
        ("clonacepan", "clonazepam"), ("ceftriasona", "ceftriaxona"),
        ("flucozanol", "fluconazol"), ("amoxacilina", "amoxicilina"),
        ("prednizona", "prednisona"), ("gentamisina", "gentamicina"),
        ("lozartan", "losartan"),
    ],
    "cruces_de_categoria": [
        ("vivacina", "vitamina"), ("todo", "dove"), ("tarda", "venda"),
        ("terapia", "tortilla"), ("morfina", "formina"),
        ("captopril", "carotida"), ("insulina", "insultos"),
    ],
}


def _semilla_sql(root: Path) -> list[dict]:
    """Lee los pares alias→canónico del SQL real de la migración 012."""
    sql = root / "migrations" / "012_med_aliases.sql"
    if not sql.exists():
        return []
    texto = sql.read_text(encoding="utf-8")
    pares = re.findall(r"\(\s*'([^']+)'\s*,\s*'([^']+)'\s*,\s*'([^']+)'", texto)
    return [{"alias": a, "canonico": c, "origen": o} for a, c, o in pares]


def _relevancia(root: Path) -> dict:
    from app.relevancia import es_relevante, filtrar_relevantes

    out: dict = {}
    out["caso1_relevancia_por_producto"] = {
        p["nombre"]: es_relevante(
            "amor nitrofurantoina 50mg vitamina", p["nombre"]
        )
        for p in CATALOGO_C1
    }
    out["caso1_filtrados"] = [
        p["nombre"]
        for p in filtrar_relevantes("amor nitrofurantoina 50mg vitamina", CATALOGO_C1)
    ]
    out["caso2_relevancia_por_producto"] = {
        p["nombre"]: es_relevante("vivacina", p["nombre"]) for p in CATALOGO_C2
    }
    out["caso2_filtrados"] = [
        p["nombre"] for p in filtrar_relevantes("vivacina", CATALOGO_C2)
    ]
    out["typo_ok"] = {
        typo: es_relevante(typo, nombre) for typo, nombre in TYPO_OK
    }
    out["falsos_positivos"] = {
        term: es_relevante(term, nombre) for term, nombre in FALSO_POSITIVO
    }
    out["caso4_filtrados"] = [
        p["nombre"] for p in filtrar_relevantes("solunoval solución bucal", CATALOGO_C4)
    ]
    return out


def _extraccion(root: Path) -> dict:
    import app.turn as turn

    out: dict = {}
    for nombre, texto in (("caso1", CASO_1), ("caso2", CASO_2),
                          ("caso3", CASO_3), ("caso4", CASO_4)):
        out[f"{nombre}_termino_unico"] = turn._extraer_termino_medicamento(texto)
        out[f"{nombre}_parece_lista"] = turn._parece_lista_medicamentos(texto)
        out[f"{nombre}_multi"] = turn._partir_consulta_multi(texto)
    # F14.2 — opción numerada en mensaje mixto.
    fn_opcion = getattr(turn, "_menciona_opcion_numerada", None)
    if fn_opcion is None:
        out["caso3_menciona_opcion"] = "no existe en este árbol"
    else:
        out["caso3_menciona_opcion"] = fn_opcion(CASO_3)
        out["opcion_negativos"] = {
            t: fn_opcion(t)
            for t in ["la opción es buena", "dame opciones", "quiero 2 cajas",
                      "opción 11 y 12", "de la opción 9"]
        }
    out["caso3_eleccion_multiple"] = turn._extraer_eleccion_multiple(CASO_3)
    # F14.5 — consultas que NO deben partirse (co-formulación / un solo fármaco).
    out["no_parte"] = {
        t: turn._partir_consulta_multi(t)
        for t in [
            "tienes atamel y su precio",
            "amoxicilina y acido clavulanico",
            "vitamina c y zinc",
            "disponen de clopidogrel de 75 losartan de 50 atorvastatina de 30",
        ]
    }
    return out


def _alias(root: Path) -> dict:
    try:
        from app.aliases import cargar_items, reescribir, total
    except ModuleNotFoundError:
        return {"alias_modulo": "no existe en este árbol"}
    n = cargar_items(_semilla_sql(root))
    return {
        "alias_modulo": "ok",
        "pares_sembrados": n,
        "total_registrado": total(),
        "solunoval": reescribir("solunoval"),
        "solunoval_dosis": reescribir("solunoval 500 mg"),
        "solunoval_bucal": reescribir("solunoval solución bucal"),
        "typo_del_log": reescribir("fexofenasina"),
        "typo_dos_ediciones": reescribir("lorsatan"),
        "marca_no_se_toca": reescribir("macrodantina"),
        "frase_larga_no_aplica": reescribir("solunoval mas otra cosa"),
        "vitamina_b": reescribir("bitamina c"),
    }


def _matriz(root: Path) -> dict:
    """Matriz de decisión del guard de typo: métricas + veredicto REAL.

    Las métricas (distancia, prefijo, desplazamiento) se calculan aquí con el
    mismo algoritmo que `app/relevancia.py`, para poder medir también el árbol
    PREVIO. El veredicto, en cambio, lo da la función real del árbol bajo prueba
    (`es_relevante`), y — cuando existe el parámetro — también su versión LAXA
    (`typo_estricto=False`), que es el comportamiento anterior a F14.
    """
    from app.relevancia import es_relevante

    def lev(a: str, b: str) -> int:
        if a == b:
            return 0
        fila = list(range(len(b) + 1))
        for i, ca in enumerate(a, 1):
            nueva = [i]
            for j, cb in enumerate(b, 1):
                nueva.append(min(fila[j] + 1, nueva[j - 1] + 1,
                                 fila[j - 1] + (ca != cb)))
            fila = nueva
        return fila[-1]

    def prefijo(a: str, b: str) -> int:
        n = 0
        for ca, cb in zip(a, b):
            if ca != cb:
                break
            n += 1
        return n

    def desplazamiento(a: str, b: str) -> bool:
        """Un carácter que se mueve de sitio (F14.4): mismo algoritmo que app/."""
        if a == b or len(a) != len(b):
            return False
        n = len(a)
        for i in range(n):
            movido = a[i]
            sin = a[:i] + a[i + 1:]
            for j in range(n):
                if sin[:j] + movido + sin[j:] == b:
                    return True
        return False

    def fila(a: str, b: str) -> dict:
        producto = b.upper()
        out = {
            "dist": lev(a, b),
            "prefijo": prefijo(a, b),
            "desplazamiento": desplazamiento(a, b),
            "es_relevante": es_relevante(a, producto),
        }
        try:
            out["es_relevante_laxo"] = es_relevante(a, producto, typo_estricto=False)
        except TypeError:
            out["es_relevante_laxo"] = "no existe el parámetro en este árbol"
        return out

    return {
        grupo: {f"{a}->{b}": fila(a, b) for a, b in pares}
        for grupo, pares in MATRIZ.items()
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".", help="raíz del árbol a simular")
    ap.add_argument("--out", default="", help="archivo JSON de salida")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    sys.path.insert(0, str(root))
    datos = {"root": str(root)}
    datos["extraccion"] = _extraccion(root)
    datos["relevancia"] = _relevancia(root)
    datos["alias"] = _alias(root)
    datos["matriz_typo"] = _matriz(root)
    texto = json.dumps(datos, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(texto, encoding="utf-8")
        print(f"escrito {args.out}")
    else:
        print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
