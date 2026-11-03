# F15 — Capa de comprensión del acto de conversación (reporte del cambio)

**Qué es:** el cambio que impide que el agente busque en el catálogo antes de entender qué le
están diciendo. Responde a las quejas del cliente (oct-2026) y a la directriz *«no quiero atarlo a
una regla específica por palabras: que diferencie primero las conversaciones y luego entienda cuál
es el medicamento»*.

**Estado:** implementado, medido y commiteado en `desarrollo` (`88bfd86`, `2b5cdfa`).
Pendiente: veredicto del diagnóstico independiente (sección 6).

---

## 1. Las quejas y su causa raíz

| Queja (verbatim) | Qué hacía el agente |
|---|---|
| «No puede ser Indu.» (habla del laboratorio) | Contestó **«⚠️ No tengo SER INDU»** |
| «Vivo en Ciudad Bolivar.» (dónde vive) | **13 consultas al catálogo**: `vivo ciudad bolivar` → transposiciones → `boliva`, `boliv`, `boli`, `bol` |
| «Solo una marca?» (pregunta por el atributo) | Buscó el término `marca` |
| «Por ahroa no» (negativa temporal) | Buscó el término `ahroa` |

**Causa raíz medida** (no teórica): la decisión de buscar la tomaba un heurístico de **forma**
(`_parece_consulta_medicamento` → `_parece_nombre_producto`): «sin `?`, ≤4 palabras, ninguna de
saludo y una palabra de ≥5 letras ⇒ buscar». «Vivo en Ciudad Bolivar.» cumple las cuatro. Y la
bandera que lo habilitaba, `hay_senal_de_farmaco`, devolvía **True en 4 de las 5 frases basura**
(`tokens_farmaco` es, en la práctica, «cualquier palabra de ≥4 letras»: `indu` contaba como fármaco).

**Reproducido end-to-end con el modelo de producción** (`deepseek/deepseek-v4.1-flash`):
`eval/f15-frases-conversacion/antes-deepseek-v4.1-flash.{json,md}` — incluido el «No tengo SER INDU»
literal, y las 13 consultas de «Ciudad Bolivar» (el cliente no las ve, pero contaminan
`med_queries`, de donde F14.4 deriva alias y correcciones).

## 2. Qué se implementó

**`app/intencion.py`** — la capa. Clasifica el acto de conversación (`saludo`, `cortesia`,
`dato_personal`, `atributo_producto`, `dilatoria`, `reclamo`, `consulta_medicamento`, `otro`) y
decide `hay_consulta` + `termino`, con **tres caminos** para no pagar una llamada donde hoy se
acierta:

| Camino | Cuándo | Coste |
|---|---|---|
| `consulta` | verbo explícito («tienen», «precio de», «busco»…) | 0 (determinista) |
| `nombre` | nombre pelado corto («shampo dreene», «vivacina») | 0 (determinista) |
| `capa` | todo lo demás: frases, datos personales, atributos, dudas | 1 llamada |
| `fail-safe` | timeout, proveedor caído, JSON inválido, capa apagada | 0 (conducta anterior) |

**Integración en `app/turn.py`** — la capa es el **decisor** del backstop (antes lo era el
heurístico de forma, que sobrevive solo en el camino de fail-safe). No se gasta llamada si el LLM
ya consultó el catálogo.

**Configuración** — `INTENT_LAYER` (default `true`), `INTENT_MODEL` / `INTENT_API_KEY` /
`INTENT_BASE_URL` (proveedor propio opcional, mismo patrón que sus `VISION_*`: vacío = modelo del
chat), `INTENT_TIMEOUT` (12 s).

**Auditoría** — migración `014_med_queries_intent.sql`: `med_queries` gana `intent_fuente`,
`intent_acto`, `intent_motivo`, `intent_confianza`. Si la búsqueda la pidió el **modelo por su
cuenta** (tool call, no el backstop), la fila se marca `llm` — así toda búsqueda es atribuible y se
puede medir **quién** buscó basura.

**Restricciones respetadas:** `app/guards.py` sin un solo cambio, cadena de vetos intacta, cambios
aditivos, nada tocado fuera del repo.

## 3. Evidencia

| Nivel | Qué | Resultado |
|---|---|---|
| Compilación | `py_compile app/*.py` | OK (25 módulos) |
| Tests | `pytest tests -q` | **144 en verde** (25 nuevos de la capa) |
| Corpus real | 40 frases (20 que no deben buscar / 20 consultas legítimas) con `deepseek/deepseek-v4.1-flash` | **40/40 · 0 falsos positivos · 0 falsos negativos** |
| Robustez | el mismo corpus con `z-ai/glm-4.7` (otra familia) | **40/40** |
| Contenedor | `docker compose build nea` + arranque | migración `014` aplicada, health OK |
| End-to-end | escenarios 12/13 (código real, modelo real, catálogo controlado) | **cero consultas al catálogo** para las frases queja |

Artefactos: `corpus-deepseek_deepseek-v4.1-flash.json`, `corpus-z-ai_glm-4.7.json`,
`antes-deepseek-v4.1-flash.{json,md}` (el «antes»), `despues.md` (el «después»), `probe_capa.py`
(sonda determinista), `medir_corpus.py`, `diagnostico_sonnet.py`.

**Lo que el corpus destapó y se corrigió en el camino:** la primera medición dio 82.5% por dos
motivos distintos — (a) truncamiento de mi propio medidor (`max_tokens=300`, artefacto de medición,
no de la capa) y (b) **consultas por categoría o síntoma** («busco algo para el dolor de cabeza»,
«hay crema para las manchas?») que la capa clasificaba como charla. Añadidas al prompt como
consulta con término de categoría: 92.5% → **100%**. Ese hallazgo no estaba en el spec.

## 4. Cómo se comporta ahora (conversación real, escenario 13)

> **Cliente:** tienen macrodantina? → *(lista MACRODANTINA)*
> **Cliente:** No puede ser Indu.
> **Agente:** «No tengo información confirmada sobre ese medicamento en este momento… déjame
> buscarlo en el catálogo. ¿Cuál es…» *(sin «No tengo SER INDU», sin buscar)*
> **Cliente:** Solo una marca? → responde sobre la marca del producto y el genérico, sin buscar
> **Cliente:** Por ahroa no → «Entendido, sin problema…» *(sin buscar)*

## 5. Límites declarados

1. **El camino rápido no es una lista negra, pero existe.** Lo que decide es la capa; el camino
   rápido solo resuelve los casos sin duda razonable (verbo explícito o nombre pelado). Aun así,
   su `_PALABRAS_CONVERSACION` es una lista corta: sirve para **desviar** a la capa, no para decidir.
2. **El modelo del chat conserva su propia herramienta.** La capa gobierna el backstop; si el
   modelo decide llamar `buscar_medicamento` por su cuenta con un término basura, nadie lo detiene
   todavía (antes sí pasaba: `ladrones`, `estafa`, `puedo devolverlas` en el log). Ahora al menos
   queda auditado como `fuente='llm'`. **Es el candidato natural a F16.**
3. **Coste.** Una llamada extra por turno **solo** en el camino `capa`. Medido: ~2 s por llamada;
   en el corpus, las consultas con verbo o nombre pelado no pagan nada.
4. **Oscilación del modelo.** Como en F14, las corridas sin `temperature=0` varían; por eso cada
   caso se mide con corpus (40 frases) y no con una sola conversación.
5. **El Laboratorio local no puede medir esto**: sin credenciales de Firebase el catálogo responde
   vacío y el Laboratorio mide estilo (±14 entre corridas idénticas), no precisión de búsqueda.

## 6. Diagnóstico independiente (pendiente de cerrar)

Pedido explícito del cliente: que un revisor externo (**Sonnet**) juzgue si el cambio quedó bien
hecho. El script `diagnostico_sonnet.py` envía al revisor el código de la capa, el diff focalizado,
la integración en el turno, los nombres de los tests, la evidencia del corpus y los escenarios, con
8 preguntas concretas (corrección, modos de fallo, ¿cubre solo el backstop?, coste, testabilidad,
diseño, auditoría, riesgo de falsos negativos).

Estado: las llamadas a `anthropic/claude-sonnet-5.5`/`sonnet-5`/`sonnet-4.6` vía el proxy Nous
devuelven **502/429 «model temporarily at capacity upstream»** (no es el tamaño del payload: 24k
caracteres pasa, 30k con reintentos no). Se reintenta; si la capacidad no se recupera, el revisor
será `openai/gpt-6-astra-pro` (mismo rol, otro proveedor) y quedará dicho aquí.
