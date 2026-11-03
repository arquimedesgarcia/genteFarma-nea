"""F15 — Capa de comprensión del acto de conversación.

**Para qué existe.** El agente de farmacia buscaba en el catálogo antes de entender
qué le estaban diciendo. Quejas reales (oct-2026), reproducidas:

- «No puede ser Indu.» (el cliente habla del LABORATORIO) → el agente contestó
  «⚠️ No tengo SER INDU».
- «Vivo en Ciudad Bolivar.» (dónde vive) → 13 consultas al catálogo en un turno
  (`vivo ciudad bolivar` → transposiciones → `boliva`, `boliv`, `boli`, `bol`),
  contaminando `med_queries` (de donde se derivan los alias de F14.4).
- «Solo una marca?» → término `marca`; «Por ahroa no» → término `ahroa`.

El decisor anterior era un heurístico de FORMA (`turn._parece_nombre_producto`):
«sin '?', ≤4 palabras, ninguna de saludo y una palabra de ≥5 letras» ⇒ se buscaba.
Eso acepta cualquier oración, y ninguna lista negra lo arregla de forma estable
(«Shampo Dreene» DEBE buscar y «Vivo en Ciudad Bolivar» NO, con los mismos rasgos).

**Qué hace esta capa.** Decide, antes de buscar: ¿el mensaje trae una consulta de
medicamento, y cuál es el término? Es decir, primero entiende el acto de
conversación (saludo, cortesía, dato personal, pregunta de atributo, dilatoria,
reclamo, consulta de medicamento, otro) y solo entonces se busca. En la duda,
pregunta en vez de buscar.

**Cómo lo hace, en tres caminos** (para no pagar una llamada en cada turno):

1. `consulta` — camino rápido: hay verbo explícito de consulta ("tienen", "precio
   de", "busco"...). Un pedido explícito se busca: si el término es basura, la
   respuesta honesta es «no lo tengo», que es lo correcto para un pedido.
2. `nombre` — camino rápido: mensaje corto (1–2 palabras) con forma de nombre
   pelado y sin ninguna palabra conversacional conocida («shampo dreene»,
   «vivacina»). Es el caso que motivó el heurístico de forma original.
3. `capa` — LLM: todo lo demás (mensajes con contexto, frases, dudas). Una sola
   llamada con contrato JSON cerrado. Es el único camino que cuesta dinero y solo
   se paga donde el heurístico adivinaba.

**Fail-safe.** Si la capa no responde (timeout, proveedor caído, JSON inválido),
`hay_consulta=None` y el llamador conserva el comportamiento anterior. La mejora
se mide con la capa viva; un proveedor caído no cambia el flujo.

**Auditoría.** Cada veredicto lleva `fuente`, `acto`, `motivo` y `confianza`, y el
turno los guarda junto a la búsqueda (`med_queries`) para poder medir la capa y
saber a quién culpar (¿entendió mal la capa o falló el catálogo?) en un caso real.

No toca `guards.py` ni la cadena de vetos: decide ANTES de la búsqueda; los vetos
siguen siendo la última palabra sobre la respuesta.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from app.llm import OpenAiLlm

logger = logging.getLogger("nea.intencion")

# Actos de conversación que la capa reconoce. `consulta_medicamento` es el único
# que dispara búsqueda; el resto se responde conversacionalmente.
ACTOS = (
    "saludo",
    "cortesia",
    "dato_personal",
    "atributo_producto",
    "dilatoria",
    "reclamo",
    "consulta_medicamento",
    "otro",
)

# Verbos/frases de consulta EXPLÍCITA. No es una lista negra: es el camino rápido
# de alta precisión. Un mensaje con verbo de consulta es un pedido, y ante un
# pedido la conducta correcta es buscar (si el nombre está mal, "no lo tengo" es
# una respuesta honesta, no un error de comprensión).
_VERBO_CONSULTA = re.compile(
    r"\b("
    r"tienen|tienes|tenga|hay|habra|habra|venden|vende|manejan|maneja|traen|trae|"
    r"busco|buscando|buscar|necesito|necesita|requiero|quiero saber|sabes si|"
    r"precio|precios|cuanto|cuánto|vale|cuesta|sirve|sirven|disponible|disponibles|"
    r"existe|consigo|consigues|donde|dónde|tendran|tendrán|me das|me vendes"
    r")\b"
)

# Palabras que, si aparecen, mandan el mensaje a la CAPA en vez de al camino
# rápido de "nombre pelado": son palabras de conversación, no de producto.
# (Solo desvían la decisión hacia el modelo; NO deciden por sí mismas.)
_PALABRAS_CONVERSACION = {
    "vivo", "vives", "vive", "ciudad", "estado", "calle", "avenida", "sector",
    "marca", "marcas", "laboratorio", "laboratorios", "generico", "genérico",
    "original", "india", "indu", "chino", "chinos", "nacional", "importado",
    "ahora", "ahroa", "hoy", "manana", "mañana", "luego", "despues", "después",
    "gracias", "hola", "buenas", "buenos", "tardes", "noches", "saludos",
    "listo", "ok", "okay", "dale", "perfecto", "claro", "igual", "entonces",
    "cuenta", "banco", "pago", "pagare", "pagaré", "efectivo", "zelle", "pago movil",
    "receta", "medico", "médico", "doctora", "doctor", "consultorio",
    "bendicion", "bendición", "dios", "familia", "hijo", "hija", "mama", "mamá",
}
_PALABRAS_CONVERSACION = {re.sub(r"[áéíóú]", lambda m: "aeiou"["áéíóú".index(m.group())], p)
                          for p in _PALABRAS_CONVERSACION}

_SISTEMA = """Eres la etapa de COMPRENSIÓN de un asistente de farmacia por WhatsApp.
Tu único trabajo: decir si el mensaje del cliente pide un medicamento (y cuál), o si es
conversación. NO respondes al cliente, NO buscas, NO saludas: solo clasificas.

Devuelves SOLO un objeto JSON, sin texto alrededor ni ```:
{"acto": "<uno de: saludo|cortesia|dato_personal|atributo_producto|dilatoria|reclamo|consulta_medicamento|otro>",
 "hay_consulta": true|false,
 "termino": "<texto del medicamento, o null>",
 "confianza": 0.0-1.0,
 "motivo": "<máximo 12 palabras>"}

Reglas:
- `hay_consulta` es true SOLO si el cliente pide/informa/consulta un medicamento concreto
  (o pregunta por su precio, existencia o presentación de forma que haga falta buscarlo).
- Ejemplos que NO son consulta (hay_consulta=false, termino=null):
  * «No puede ser Indu.» → habla del LABORATORIO del producto ya mostrado (acto=atributo_producto).
  * «Vivo en Ciudad Bolivar.» → da un dato personal (acto=dato_personal).
  * «Solo una marca?» → pregunta por el atributo del producto ya mostrado (acto=atributo_producto).
  * «Por ahroa no» → dilatoria/negativa temporal (acto=dilatoria).
  * «gracias, linda», «hola mi amor», «que Dios te bendiga» → saludo/cortesía.
- `termino` lleva SOLO el medicamento, limpio: sin verbos («tienen», «precio de», «quiero»),
  sin relleno y sin cortesías. «precio de la macrodantina de 100» → «macrodantina 100».
- Si el cliente escribe un nombre que no reconoces, pero claramente es un nombre de
  medicamento (marca o fármaco, incluso mal escrito: «vivacina», «omeprasol»), hay_consulta=true.
- Si dudas entre conversación y medicamento, pon hay_consulta=false y confianza baja:
  el asistente preguntará. Es preferible preguntar que responder sobre algo que el cliente
  no pidió."""


@dataclass
class Entendimiento:
    """Veredicto de la capa. `hay_consulta=None` = no concluyente (fail-safe)."""

    acto: str = "otro"
    hay_consulta: bool | None = None
    termino: str | None = None
    confianza: float = 0.0
    motivo: str = ""
    fuente: str = "fail-safe"  # consulta | nombre | capa | fail-safe | desactivada

    @property
    def concluyente(self) -> bool:
        return self.hay_consulta is not None


def _norm(texto: str) -> str:
    t = (texto or "").lower()
    for a, b in (("á", "a"), ("é", "e"), ("í", "i"), ("ó", "o"), ("ú", "u"), ("ü", "u")):
        t = t.replace(a, b)
    return t


def _tokens(texto: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _norm(texto))


def camino_rapido(texto: str, termino_candidato: str | None) -> Entendimiento | None:
    """Decide sin LLM cuando no hay duda razonable. `None` = hay que consultar la capa."""
    if not texto or not texto.strip():
        return Entendimiento(acto="otro", hay_consulta=False, motivo="mensaje vacío", fuente="desvio")
    t = _norm(texto)
    # 1) Pedido explícito.
    if _VERBO_CONSULTA.search(t) and termino_candidato:
        return Entendimiento(
            acto="consulta_medicamento", hay_consulta=True, termino=termino_candidato,
            confianza=0.9, motivo="verbo de consulta explícito", fuente="consulta",
        )
    # 2) Nombre pelado corto ('shampo dreene', 'vivacina', 'atamel 500').
    palabras = _tokens(texto)
    if (
        termino_candidato
        and 1 <= len(palabras) <= 2
        and all(len(p) >= 3 for p in palabras)
        and not any(p in _PALABRAS_CONVERSACION for p in palabras)
        and "?" not in texto
    ):
        return Entendimiento(
            acto="consulta_medicamento", hay_consulta=True, termino=termino_candidato,
            confianza=0.7, motivo="nombre pelado corto", fuente="nombre",
        )
    # 3) Duda: que decida la capa (frases, datos personales, mensajes con contexto).
    return None


def _extraer_json(texto: str) -> dict[str, Any] | None:
    """Saca el primer objeto JSON del texto (tolera ```json, prólogo y cola)."""
    if not texto:
        return None
    limpio = texto.strip()
    limpio = re.sub(r"^```(?:json)?|```$", "", limpio, flags=re.M).strip()
    inicio = limpio.find("{")
    if inicio < 0:
        return None
    # Recorte por llaves balanceadas (ignorando las que van dentro de cadenas).
    profundidad = 0
    en_cadena = False
    escape = False
    for i in range(inicio, len(limpio)):
        c = limpio[i]
        if en_cadena:
            if escape:
                escape = False
            elif c == "\\":
                escape = True
            elif c == '"':
                en_cadena = False
            continue
        if c == '"':
            en_cadena = True
        elif c == "{":
            profundidad += 1
        elif c == "}":
            profundidad -= 1
            if profundidad == 0:
                try:
                    datos = json.loads(limpio[inicio : i + 1])
                except Exception:
                    return None
                return datos if isinstance(datos, dict) else None
    return None


def _veredicto_desde_json(datos: dict[str, Any]) -> Entendimiento:
    acto = str(datos.get("acto") or "otro").strip().lower()
    if acto not in ACTOS:
        acto = "otro"
    crudo = datos.get("hay_consulta")
    if isinstance(crudo, str):
        crudo = crudo.strip().lower() in {"true", "si", "sí", "yes", "1"}
    hay = bool(crudo)
    termino = datos.get("termino")
    termino = str(termino).strip() if isinstance(termino, str) else None
    if termino:
        termino = re.sub(r"\s+", " ", termino).strip(" .,;:!?") or None
    try:
        confianza = float(datos.get("confianza", 0.0))
    except (TypeError, ValueError):
        confianza = 0.0
    confianza = min(max(confianza, 0.0), 1.0)
    motivo = str(datos.get("motivo") or "").strip()[:120]
    return Entendimiento(
        acto=acto,
        hay_consulta=hay,
        termino=termino if (hay and termino) else None,
        confianza=confianza,
        motivo=motivo,
        fuente="capa",
    )


_CLIENTES: dict[tuple[str, str, str], Any] = {}


def cliente_intencion(settings: Any, llm_chat: Any) -> Any:
    """Cliente de la capa: si no hay `INTENT_MODEL`, es el mismo del chat.

    Mismo patrón que `VISION_*` del árbol del cliente: la etapa puede vivir en otro
    proveedor (barato/rápido) sin tocar el modelo del chat.
    """
    modelo = str(getattr(settings, "intent_model", "") or "").strip()
    if not modelo:
        return llm_chat
    clave = (
        modelo,
        str(getattr(settings, "intent_api_key", "") or ""),
        str(getattr(settings, "intent_base_url", "") or ""),
    )
    if clave not in _CLIENTES:
        api_key = clave[1] or getattr(settings, "openai_api_key", "")
        base = clave[2] or getattr(settings, "openai_base_url", "")
        _CLIENTES[clave] = OpenAiLlm(api_key, modelo, base_url=base or None)
    return _CLIENTES[clave]


def _contexto(texto: str, termino_candidato: str | None, producto_previo: str | None) -> str:
    partes = [f"Mensaje del cliente: {texto.strip()}"]
    if producto_previo:
        partes.append(f"Producto que el asistente acaba de mostrar: {producto_previo}")
    if termino_candidato:
        partes.append(
            f"Término candidato extraído por el sistema (puede ser basura): {termino_candidato}"
        )
    partes.append("Responde SOLO con el JSON.")
    return "\n".join(partes)


async def entender(
    texto: str,
    *,
    llm: Any,
    settings: Any,
    termino_candidato: str | None = None,
    producto_previo: str | None = None,
) -> Entendimiento:
    """Veredicto sobre el mensaje: camino rápido → capa LLM → fail-safe."""
    if not bool(getattr(settings, "intent_layer", True)):
        return Entendimiento(acto="otro", hay_consulta=None, motivo="capa desactivada",
                             fuente="desactivada")
    rapido = camino_rapido(texto, termino_candidato)
    if rapido is not None:
        return rapido
    cliente = cliente_intencion(settings, llm)
    if cliente is None:
        return Entendimiento(hay_consulta=None, motivo="sin cliente LLM", fuente="fail-safe")
    timeout = float(getattr(settings, "intent_timeout", 12) or 12)
    try:
        reply = await asyncio.wait_for(
            cliente.complete(
                [
                    {"role": "system", "content": _SISTEMA},
                    {"role": "user", "content": _contexto(texto, termino_candidato, producto_previo)},
                ]
            ),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.warning("capa de comprensión: timeout de %.0fs — fail-safe", timeout)
        return Entendimiento(hay_consulta=None, motivo="timeout", fuente="fail-safe")
    except Exception as exc:  # proveedor caído, cuota, red
        logger.warning("capa de comprensión: fallo (%s) — fail-safe", exc)
        return Entendimiento(hay_consulta=None, motivo=f"fallo: {exc}"[:120], fuente="fail-safe")

    datos = _extraer_json(getattr(reply, "content", "") or "")
    if not datos:
        logger.warning("capa de comprensión: respuesta sin JSON válido — fail-safe: %r",
                       (getattr(reply, "content", "") or "")[:200])
        return Entendimiento(hay_consulta=None, motivo="JSON inválido", fuente="fail-safe")
    veredicto = _veredicto_desde_json(datos)
    logger.info(
        "capa de comprensión: acto=%s consulta=%s termino=%r confianza=%.2f (%s)",
        veredicto.acto, veredicto.hay_consulta, veredicto.termino,
        veredicto.confianza, veredicto.motivo,
    )
    return veredicto
