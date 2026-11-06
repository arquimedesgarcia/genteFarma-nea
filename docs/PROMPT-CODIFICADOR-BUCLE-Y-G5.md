# PROMPT — AGENTE CODIFICADOR: bucle de herramientas y G5 con evidencia

> Pegar este documento completo como instrucción del codificador. Son **dos paquetes
> independientes** (A y B), **uno por rama**. No mezclar los paquetes en una misma rama.
> Las líneas citadas son del commit base **`5b7815e`** (`desarrollo`): si el HEAD cambió,
> localizar por el fragmento de código, no por el número de línea.

---

## 0. Contexto y reglas del proyecto

- Repo local: `D:\Proyectos\GenteFarma\agentNEA` (agente NEA de WhatsApp para farmacia).
- Rama de trabajo y de entrega: **`desarrollo`**. Base de los dos paquetes: HEAD actual de `desarrollo` (`5b7815e`).
- Ramas ya creadas para estos paquetes: **`fix/tool-loop-exhaustion`** (paquete A) y **`fix/g5-composition-evidence`** (paquete B).
  **Ojo: hoy las dos apuntan al MISMO commit que `desarrollo` (árbol idéntico) — no tienen contenido.** El primer commit real de cada rama es tu trabajo; crear la rama no cuenta como entrega.
- Cambios **aditivos** y quirúrgicos. Nada de refactors de vecindad.

**Prohibido:**
- Reimplementar F15.1 o añadir una **segunda puerta de autorización** de búsqueda (la puerta es `tools._autorizar_busqueda` y decide por término; es la única).
- **Debilitar** un veto para que las respuestas "pasen" (ni relajar G5, ni ampliar el bypass de evidencia, ni borrar patrones).
- Tocar el dominio farmacéutico, el carrito, precios, OCR ni añadir funcionalidades ajenas al paquete.
- Modificar tests existentes para que pasen, ni borrarlos.
- Tocar `main`/`master`, `upstream`, ni borrar/reescribir ramas de otros.
- Push a `desarrollo` o a `main` de nadie: entrega tu trabajo en **tu rama** del espejo.

**Antes de escribir código:** lee `app/turn.py` (`_tool_loop`, `run_turn`, `_fallback_farmacia`), `app/tools.py` (`_autorizar_busqueda`, `ToolRuntime`), `app/guards.py` y corre las sondas de §1 para ver el defecto con tus ojos.

---

## 1. Reproducir el estado actual (coste 0: sin modelo real, sin Docker, sin CRM)

```bash
cd D:/Proyectos/GenteFarma/agentNEA
PY=D:/Proyectos/GenteFarma/agentNEA/.venv-test/Scripts/python.exe   # venv de tests del repo

$PY -m pytest tests/ -q                      # hoy: 166 passed
$PY -m py_compile app/*.py

# línea A (bucle de herramientas)  -> A1 A2 A3 A4 salen SIN RESPUESTA
$PY eval/qa-2026-11-06/sonda_bucle.py

# línea B (G5 de punta a punta)    -> B2 B4 B5 B7-5 pasan tal cual; B8-3 falso positivo
$PY eval/qa-2026-11-06/sonda_g5.py

# línea B (detectores, frase por frase)
$PY eval/qa-2026-11-06/sonda_guardas.py
```

Las sondas usan un **LLM guionado** (determinista) y un catálogo de mentira, y corren el código real
(`handle_flush → run_turn → _tool_loop → herramientas → vetos`); lo que capturan en `ctx.lab_outbox`
es lo que el cliente habría recibido. El diagnóstico completo y el estado de cada caso están en
`docs/QA-2026-11-06-bucle-de-herramientas-y-g5.md` (léelo primero: no repitas el trabajo de medición).

---

## 2. PAQUETE A — `fix/tool-loop-exhaustion`

**Objetivo único y verificable:** *ningún turno de farmacia termina sin un mensaje para el cliente*.
Hoy hay tres caminos distintos al silencio y uno de ellos revienta el turno.

### D-A1 (CRÍTICO) — el respaldo de argumentos vacíos no se `await`ea

- Dónde: `app/turn.py`, dentro de `_tool_loop`, tras contar `empty_rounds >= 3`:
  `return _fallback_farmacia(user_text, runtime, ctx, farmacia)` — y `_fallback_farmacia` es `async def`.
- Qué pasa hoy: al tercer lote de tool-calls con `arguments` vacíos se devuelve un **objeto coroutine**;
  el llamador lo trata como texto y `guards.afirma_recibir_media` lanza
  `TypeError: expected string or bytes-like object, got 'coroutine'` → `handle_flush` registra
  `turno … reventó — silencio` y **el cliente no recibe nada** (`RuntimeWarning: coroutine '_fallback_farmacia' was never awaited`).
- Esperado: se envía la respuesta de respaldo (búsqueda directa del término, o plantilla honesta si no hay término/productos).
- Criterio duro: el valor que devuelve `_tool_loop` en ese camino debe ser `str` no vacío. Añade una aserción/tipado que lo garantice y un test que lo compruebe.

### D-A2 (CRÍTICO) — agotar `MAX_TOOL_ROUNDS` sin texto deja el turno en silencio

- Dónde: `app/turn.py`, final de `_tool_loop`: `logger.warning("turno: demasiadas rondas de herramientas — corto sin texto")` → `return None`;
  y en `run_turn`, el envío está condicionado por `if final_text and final_text.strip():` (todas las
  asignaciones de respaldo de `run_turn` exigen `final_text` no vacío, así que **no rescatan** `None`).
- Qué pasa hoy: cinco rondas de llamadas **válidas** sin texto final ⇒ `None` ⇒ cero mensajes.
  Caso real medido: pedir 6 medicamentos produce **cero respuesta** (no "pérdida parcial").
- Esperado: respuesta de respaldo determinista, útil, honesta y coherente con lo obtenido:
  - si hay productos del catálogo en el turno (`runtime.last_products`): lista real (con precios USD/Bs) + `MENSAJE_SUGERIDO_CARRITO`;
  - si hubo error/ausencia: reconocer la limitación, sin inventar precio, stock ni disponibilidad;
  - conservar el rescate actual por `runtime.pide_recomendacion` **antes** del respaldo nuevo (caso "cliente describió el producto sin nombrarlo": manda la pregunta canónica).
- Reutiliza lo que ya existe (`_fallback_farmacia`, `_formatear_lista_productos`, plantillas de respaldo); no inventes un cuarto mecanismo.

### D-A3 (CRÍTICO) — bucle de re-fuerzo de la búsqueda forzada (backstop ↔ puerta F15.1)

- Dónde: `app/turn.py`, backstop de búsqueda forzada: `if term and (not runtime.consulted_catalog or (runtime.med_not_found and not runtime.catalog_retried)):`
  → `runtime.catalog_retried = True` → `await runtime.execute("buscar_medicamento", {"nombre": term})`.
- Qué pasa hoy: si el modelo responde **texto sin llamar la herramienta** y el término forzado **no queda autorizado**
  (capa de comprensión apagada, o en fail-safe por `null`/timeout/JSON inválido, o rechazo conclusivo), `runtime.consulted_catalog`
  **nunca** pasa a `True`; como la condición depende de él, el backstop **re-fuerza el mismo término en cada ronda**
  (`catalog_retried` solo acota la rama de `med_not_found`) hasta agotar las rondas → silencio.
  Medido: `backstop: forzando buscar_medicamento('principio activo daflon') — consulted=False med_not_found=False` ×5
  + `búsqueda NO autorizada por la capa: … (acto=otro, consulta=None): capa desactivada` ×5 + `corto sin texto`.
- Esperado: **un solo intento** de búsqueda forzada por término y por turno. Si la puerta no autoriza, se sale del bucle
  con la respuesta honesta que F15.1 ya prevé para ese caso (preguntar el medicamento / reconocer la limitación), **jamás repetir la ronda**.
- Restricciones: no toques `_autorizar_busqueda` ni su semántica por término; no añadas otra puerta. El arreglo es del **bucle**, no del guardián.
- Extra (BAJO, mismo sitio): `_termino_es_medicamento_plausible(term)` autoriza `"principio activo daflon"` para forzar la búsqueda mientras la puerta lo rechaza; alinea ambos criterios o documenta por qué difieren.

### D-A4 (ALTO) — no hay detección de llamadas degeneradas que repiten información

- Dónde: `app/turn.py`, contador `empty_rounds` (solo cubre lotes con `arguments` vacíos).
- Qué pasa hoy: repetir la **misma** llamada con los **mismos** argumentos (o términos equivalentes sin aportar nada nuevo) no se detecta: quema las rondas y termina en D-A2 (silencio).
- Esperado: detectar la repetición degenerada y salir **con respuesta** (no con `None`).
- Cuidado con el falso positivo: una **secuencia legítima** de búsquedas distintas (un medicamento por ronda, p. ej. 4 medicamentos distintos y luego el texto) **no** es un bucle y no debe cortarse. Criterio sugerido: solo cuentan como degeneradas las llamadas **idénticas** (misma herramienta + mismos argumentos normalizados) repetidas ≥3 veces **consecutivas**, o bien las que no cambian `runtime.last_products`/`last_options` entre rondas.

### A.5 Tests a añadir (en la rama, no tocar los existentes)

Crea `tests/harness_agente.py` (arnés reutilizable, determinista, sin modelo real: `FakeLlm` guionado
con `.content`/`.tool_calls`, `CrmStub` con el contrato de `eval/qa-2026-11-06/sonda_bucle.py`) y
`tests/test_tool_loop_respaldo.py` con, al menos, estos casos (entrada del cliente / guion del modelo / aserción):

| ID | Cliente | Guion del modelo | Aserción |
|---|---|---|---|
| A1 | `busco losartan 50 mg` | 6 búsquedas válidas distintas, nunca texto | hay **una** respuesta y no está vacía; menciona lo obtenido |
| A2 | `busco losartan 50 mg` | 6 búsquedas idénticas | hay respuesta (corte por degeneración) |
| A3 | `busco losartan 50 mg` | 6 llamadas con `arguments={}` | hay respuesta; **no** se lanza excepción; `final_text` es `str` |
| A3b | *(idem)* | *(idem)* | `handle_flush` no registra `reventó` |
| A4 | 6 medicamentos en un mensaje | 1 búsqueda válida por ronda | hay respuesta; ninguno de los medicamentos obtenidos se pierde del texto |
| A5 | `busco losartan 50 mg` | búsqueda + el catálogo devuelve error/timeout | no se inventan precio, stock ni disponibilidad; se comunica la limitación |
| A6 | idem | 2 búsquedas OK + 1 fallida | lo respaldado se conserva; lo fallido se declara |
| A7 | `busco losartan` | 4 rondas de tool + texto válido en la 5ª | se acepta el texto del modelo; **no** se sustituye por respaldo |
| A8 | flujo normal: buscar → elegir presentación → precio → carrito | guion normal | sin interferencia del mecanismo de protección |
| A9 | D-A3 | término no autorizado + modelo responde texto | el backstop fuerza **una** vez y no se repite la ronda; hay respuesta |

### A.6 Prohibiciones específicas del paquete A

- No tocar `app/guards.py` (queda intacto en esta rama).
- No cambiar `MAX_TOOL_ROUNDS` para "arreglar" el agotamiento: el cliente debe recibir respuesta **también** cuando el límite se agota.
- No silenciar el camino rápido ni ampliar la autorización de búsqueda.

---

## 3. PAQUETE B — `fix/g5-composition-evidence`

**Objetivo único y verificable:** *ninguna afirmación de composición, principio activo o equivalencia
genérica llega al cliente sin respaldo del catálogo para ESE producto* — sin bloquear la información
comercial respaldada (precio, presentación, disponibilidad, stock).

### D-B1 (CRÍTICO) — la evidencia de G5 es del TURNO, no del producto ni de la afirmación

- Dónde: `app/turn.py`, veto G5: `elif (not es_negativa_con_carrito and guards.afirma_composicion(final_text) and not runtime.last_products):`.
- Qué pasa hoy: **cualquier** resultado de catálogo del turno apaga la guarda. Con resultados **irrelevantes**
  (productos similares, no el consultado) o **parciales** (precio sí, composición no), la afirmación de
  composición/equivalencia del producto consultado **sale enviada**. Medido: B4 (`busco daflon 500` → catálogo
  devuelve otro producto → "El Daflon tiene el mismo principio activo que el Panadol." enviado) y B5
  (`busco losartan 50 mg` → "El losartan tiene el mismo principio activo que el Panadol." enviado).
- Esperado: la evidencia se evalúa **por (afirmación, producto)** contra el payload real de la herramienta:
  la afirmación solo se permite si los datos del producto que respalda la herramienta contienen esa
  información (p. ej. campo de composición/principio activo, o el término presente en los datos del producto
  devuelto). Sin ese dato en el payload → **no hay respaldo** → la afirmación no se envía.
  Criterio **fail-closed**: si el esquema del catálogo no expone composición, ninguna afirmación de composición
  se permite; el catálogo de hoy (`producto`, `nombre`, `precio`, `precioBs`, `presentacion`, `productId`,
  `laboratorio`) **no** respalda composición.
- Al reemplazar, **conserva la información comercial respaldada** (precio/presentación/opciones ya listadas);
  el veto no puede vaciar la respuesta.
- Aplica el mismo criterio a las afirmaciones de precio/stock que hoy dependen de booleanos de turno
  (`not runtime.last_products` en G6, `not runtime.consulted_catalog` en G10a): como mínimo, deja el
  comportamiento documentado y con tests; no lo empeores.
- B6 (varios medicamentos): la evaluación debe ser **por producto**, no global.

### D-B2 (CRÍTICO) — redacciones de equivalencia que evaden G5

- Dónde: `app/guards.py`, `AFIRMA_COMPOSICION` (el detector de G5) + la cadena de vetos de `app/turn.py`.
- Detecta hoy: "su principio activo es…", "tiene el mismo principio activo…", "es el genérico **de**…",
  "su ingrediente activo…", "contiene X".
- **No** detecta (y sale al cliente): "es equivalente a…", "equivale a…", "es el genérico **del**…",
  "el genérico es…", "tiene el mismo efecto que…", "se puede reemplazar por…", "es el mismo medicamento que…",
  "lleva X", "tiene X".
- Esperado: cubrir las variantes afirmativas de equivalencia/composición sin ampliar a usos inocentes
  (ver D-B4). Añade la tabla de frases como test parametrizado.

### D-B3 (MEDIO) — la alternativa "composición" del regex es inerte

- Dónde: `app/guards.py`, alternativa `composici[oó]n\s+\w` dentro de un grupo cerrado por `\b`:
  tras `\w` el `\b` exige fin de palabra, así que solo casaría una palabra de **una** letra.
- Consecuencia: "su composición incluye X" y "la composición del Daflon es Y" **no se detectan** (ni con tilde ni sin ella).
- Esperado: arreglar el patrón y **normalizar tildes** en el detector (el resto del repo normaliza; los modelos
  escriben "composicion" y "composición" indistintamente). Añade regresiones en las dos grafías.

### D-B4 (MEDIO) — falsos positivos: preguntar o negar composición no es afirmarla

- Hoy: el agente **preguntando** "¿Cuál es el principio activo que buscas?" es vetado y sustituido por la plantilla
  de composición; "No puedo confirmar el principio activo sin datos del catálogo." también se detecta.
- Esperado: el veto exige **modo afirmativo** (excluye interrogativas y negaciones/limitaciones honestas).
  El cliente no debe recibir un bloqueo cuando el agente no afirmó nada farmacológico.

### B.5 Tests a añadir (en la rama)

`tests/test_g5_evidencia.py` con el arnés de §A.5 (mismos fakes; añade al `CrmStub` payloads con y sin
campo de composición para poder medir "con evidencia" vs "sin evidencia"):

| ID | Cliente | Evidencia del catálogo | Texto del modelo | Aserción |
|---|---|---|---|---|
| B1 | "¿qué principio activo tiene el daflon?" | ninguna herramienta | "Su principio activo es la diosmina." | **no** se envía principio activo |
| B2 | "¿cuál es el genérico del panadol?" | ninguna | "Es equivalente al Panadol, mismo efecto." | no se envía equivalencia |
| B3 | idem | payload **con** composición que sí respalda | "Su principio activo es X" | se permite **solo** lo respaldado |
| B4 | "busco daflon 500" | productos irrelevantes | "El Daflon tiene el mismo principio activo que el Panadol." | sigue bloqueado |
| B5 | "busco losartan 50 mg" | precio sí, composición no | "El losartan tiene el mismo principio activo que el Panadol." | bloqueado; el precio/lista respaldados se conservan |
| B6 | dos medicamentos | evidencia de uno solo | afirma composición de **los dos** | se bloquea solo el no respaldado |
| B7 | variantes | ninguna | 6 redacciones afirmativas (lista de D-B2) | todas bloqueadas |
| B8 | variantes | ninguna | pregunta / negación / limitación honesta | **ninguna** bloqueada |
| B9 | comercial | catálogo real | búsqueda, precios, disponibilidad, presentación | G5 no interfiere; texto intacto |

### B.6 Prohibiciones específicas del paquete B

- No convertir G5 en un bloqueo indiscriminado: B3 y B9 deben quedar verdes.
- No borrar plantillas ni relajar patrones para "hacer pasar" una respuesta; el arreglo es más exigente, no menos.
- No tocar la puerta de autorización de búsqueda (F15.1): esto es un veto, no una autorización. `app/guards.py` sigue siendo la última palabra sobre la respuesta.

---

## 4. Criterios de aceptación y entrega (por rama)

1. `PY -m pytest tests/ -q` → **todo verde** (los 166 existentes + los nuevos). No se modifica ningún test existente.
2. `PY -m py_compile app/*.py` → OK.
3. Las sondas de `eval/qa-2026-11-06/` **después** del cambio:
   - A: A1, A2, A3, A4 pasan de "silencio" a **respuesta enviada** (y A3 sin excepción); A7 y C0 siguen enviando texto.
   - B: B2, B4, B5, B7-5 dejan de llegar tal cual; B8-3 deja de ser falso positivo; B9 sigue tal cual.
4. Evidencia **commiteada en la rama**: `eval/qa-2026-11-06/RESULTADO-A.md` o `RESULTADO-B.md` con
   la salida **literal** de las sondas y de `pytest` (antes y después), y la lista de casos de la tabla con PASS/FAIL.
   Un caso no ejecutado no puede declararse PASS.
5. Commit(s) pequeños y quirúrgicos en la rama, mensaje en español con el prefijo del repo (`fix(...)`, `test(...)`, `eval(...)`).
   Entrega: push de **tu rama** al espejo y aviso de vuelta. **No** toques `desarrollo`, `main` ni `upstream`.
6. Reporta: qué defecto cierra cada cambio (D-A*/D-B*), archivo y función, riesgo introducido, qué **no** ejecutaste y por qué.

**Un agente que responde menos, pero no inventa información farmacológica y nunca abandona al cliente sin una respuesta controlada, es preferible a uno aparentemente más conversacional que genera información no respaldada.** Esa es la prioridad si tienes que elegir entre bloquear y responder.
