"""Diagnóstico independiente con Sonnet sobre el CAMBIO DE CÓDIGO (F15).

Envía a `anthropic/claude-sonnet-5.5` (vía proxy Nous) el diff real del cambio, la
capa completa, sus tests, la evidencia medida (corpus + escenarios) y la spec, y
pide un juicio de calidad técnico: ¿está bien hecho el cambio? ¿qué falla?

Uso: python eval/f15-frases-conversacion/diagnostico_sonnet.py [--model anthropic/claude-sonnet-5.5]
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROXY = os.environ.get("INTENT_PROXY", "http://127.0.0.1:11500/v1")


def _leer(ruta: str, limite: int = 60000) -> str:
    p = os.path.join(RAIZ, ruta)
    if not os.path.exists(p):
        return f"(no existe: {ruta})"
    with open(p, encoding="utf-8", errors="replace") as fh:
        return fh.read()[:limite]


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=RAIZ, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=120).stdout
    except Exception as exc:
        return f"(git falló: {exc})"


SISTEMA = """Eres un revisor de código senior, escéptico e independiente. Juzgas el cambio de OTRO
agente sobre un agente conversacional de farmacia (WhatsApp, Python, asyncio). No halagues: si algo
está mal, dilo; si está bien, dilo sin adornos. Si algo no se puede juzgar con la evidencia, dilo.
Responde en español, con secciones y listas, sin relleno."""

PREGUNTA = """# Qué tienes delante

Un cambio de código (F15) que añade una **capa de comprensión del acto de conversación** antes de
buscar medicamentos en el catálogo. Motivo: quejas reales (oct-2026) de que el agente confundía
frases de conversación con medicamentos — «No puede ser Indu.» (laboratorio) → el agente contestó
«⚠️ No tengo SER INDU»; «Vivo en Ciudad Bolivar.» → 13 consultas al catálogo en un turno
(`vivo ciudad bolivar` y luego transposiciones y truncamientos `boliva`, `boliv`, `boli`, `bol`);
«Solo una marca?» → buscó `marca`; «Por ahroa no» → buscó `ahroa`.

Directriz del dueño del producto: **no** quiere reglas por palabra; quiere que el agente
"entienda primero la conversación y después el medicamento".

# Evidencia medida (te la adjunto cruda)

- Corpus de 40 frases (20 que no deben buscar, 20 consultas legítimas) contra `entender()` con
  el modelo real: **40/40 = 100%**, 0 falsos positivos (basura buscada) y 0 falsos negativos
  (consulta legítima tratada como charla).
- 144 tests en verde (25 nuevos de esta capa).
- Escenarios de conversación end-to-end (código real + modelo real + catálogo controlado).

# Preguntas exactas

1. ¿El cambio **resuelve** las 4 quejas? ¿Por qué sí o por qué no, mirando el código?
2. **Modos de fallo**: recorre el código y enumera fallos reales (no teóricos): fail-safe,
   timeout, JSON inválido, capa apagada, mensajes vacíos, audios, OCR, contexto de conversación,
   el modelo del chat llamando la herramienta por su cuenta, `intent_model` mal configurado,
   concurrencia/caché del cliente, y cualquier otro que veas.
3. **¿Cubre SOLO el backstop determinista?** Si el modelo del chat decide llamar la herramienta de
   búsqueda con un término basura, ¿lo detiene algo? ¿Es un agujero real o aceptable? ¿Qué harías?
4. **Coste y latencia**: ¿el camino rápido está bien elegido? ¿Se paga una llamada donde no hace
   falta? ¿Qué pasa si `intent_timeout` vence siempre?
5. **Testabilidad y mantenibilidad**: ¿los tests prueban lo importante o lo fácil? ¿Qué test falta?
6. **Diseño**: ¿es la arquitectura correcta (decisor antes de buscar) o hay una forma
   estructuralmente mejor? ¿Se está escondiendo una lista negra disfrazada en `camino_rapido`?
7. **Auditoría**: la migración 014 añade columnas a `med_queries`; ¿es suficiente para medir la
   capa en producción y para saber si el fallo fue de comprensión o de catálogo?
8. **Riesgo de falsos negativos**: ¿qué frases legítimas podrían quedar fuera por este diseño?

Cierra con: veredicto (¿está bien hecho el cambio? sí/no/condicional), nota 0-10, y **las mejoras
concretas que aplicarías**, en orden de prioridad, cada una con: qué archivo/función tocar, qué
cambio exacto y por qué. Sé específico: quiero poder aplicarlas tal cual.
"""


def _cuerpo(argv: list[str]) -> dict:
    partes = [
        "\n\n---\n\n# ANEXO 1 — Código de la capa (app/intencion.py, completo)\n\n```python\n"
        + _leer("app/intencion.py") + "\n```",
        "\n\n---\n\n# ANEXO 2 — Diff del cambio (git diff, sin docs)\n\n```diff\n"
        + _git("diff", "fc8c026", "HEAD", "--", "app", "migrations", "tests")[:40000] + "\n```",
        "\n\n---\n\n# ANEXO 3 — Integración en el turno (fragmento real)\n\n```python\n"
        + _fragmento_turno() + "\n```",
        "\n\n---\n\n# ANEXO 4 — Tests de la capa\n\n```python\n"
        + _leer("tests/test_f15_intencion.py") + "\n```",
        "\n\n---\n\n# ANEXO 5 — Evidencia del corpus (medición real)\n\n```json\n"
        + _corpus_json() + "\n```",
        "\n\n---\n\n# ANEXO 6 — Escenarios de conversación end-to-end\n\n"
        + _leer("eval/f15-frases-conversacion/despues.md", 20000),
        "\n\n---\n\n# ANEXO 7 — Spec de F15 (diagnóstico y diseño)\n\n"
        + _leer("docs/F15-diagnostico-frases-de-conversacion.md"),
    ]
    return {
        "model": argv_modelo,
        "messages": [
            {"role": "system", "content": SISTEMA},
            {"role": "user", "content": PREGUNTA + "".join(partes)},
        ],
        "max_tokens": 8000,
    }


def _fragmento_turno() -> str:
    """El bloque de decisión del backstop, tal como quedó."""
    fuente = _leer("app/turn.py", 500000)
    marca = "F15 — LA CAPA DE COMPRENSIÓN DECIDE ANTES DE BUSCAR"
    i = fuente.find(marca)
    return fuente[max(0, i - 400) : i + 3200] if i >= 0 else "(no encontrado)"


def _corpus_json() -> str:
    for nombre in os.listdir(os.path.join(RAIZ, "eval", "f15-frases-conversacion")):
        if nombre.startswith("corpus-") and nombre.endswith(".json"):
            d = json.load(open(os.path.join(RAIZ, "eval", "f15-frases-conversacion", nombre),
                               encoding="utf-8"))
            d.pop("filas", None)  # el detalle va aparte; aquí el resumen + fallos
            return json.dumps(d, ensure_ascii=False, indent=2)
    return "{}"


argv_modelo = "anthropic/claude-sonnet-5.5"


def main() -> int:
    global argv_modelo
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="anthropic/claude-sonnet-5.5")
    args = ap.parse_args()
    argv_modelo = args.model
    req = urllib.request.Request(f"{PROXY}/chat/completions",
                                data=json.dumps(_cuerpo(sys.argv)).encode(),
                                headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=900) as r:
        datos = json.loads(r.read())
    texto = (datos.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    destino = os.path.join(RAIZ, "eval", "f15-frases-conversacion", "diagnostico-sonnet-codigo.md")
    with open(destino, "w", encoding="utf-8") as fh:
        fh.write(f"# Diagnóstico independiente del cambio F15 — {args.model}\n\n{texto}\n")
    print("usage:", json.dumps(datos.get("usage") or {}, ensure_ascii=False)[:200])
    print("guardado:", destino)
    print()
    print(texto)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
