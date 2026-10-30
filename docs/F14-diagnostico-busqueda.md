# F14 — Diagnóstico: respuestas imprecisas del agente (4 casos reales)

Fecha: 2026-09-30 · Rama: `desarrollo` · Simulaciones ejecutadas contra el código
determinista (`app/relevancia.py`, `app/turn.py`) con los 4 textos reales del
cliente. Resultados crudos al final.

## Causas raíces (verificadas por simulación, no suposición)

### C1 — Apelativos de cortesía en TEXTO ESCRITO no se limpian
`_MULETILLAS_HABLA` (turn.py:3073) contiene "amor", pero SOLO se aplica en
`_extraer_termino_transcripcion` (notas de voz). En texto escrito,
`_extraer_termino_medicamento` NO lo usa: extrajo **"amor nitrofurantoina 50mg
vitamina"**. Consecuencias en cadena:
- El token "amor" (4 letras ≥ _MIN_LEN_SENAL=5? no, pero pasa por prefijo/typo)
  valida "TE AMO PRESERV. 3PCS" (un preservativo) como resultado relevante.
- "querer" y "opción" también pasan como tokens de fármaco (C3).
- "vitamina" sin letra (C) matchea VITAMINA K igual que VITAMINA C.

### C2 — Fuzzy de 2 ediciones sobre 1 token es demasiado permisivo
`es_relevante`: "vivacina" → "vitamina" a distancia de edición 2 (v→t, c→m).
El producto más parecido NO es VITAMINA; con un índice de sinónimos/alias y
ranking por longitud de token compartido, "vivacina" debería resolver mejor
(probablemente a un antibiótico o a "no encontrado + preguntar", nunca a
vitaminas). Además: un solo token de 8 letras con 2 typos arbitrarios no debe
permitir saltar de categoría terapéutica.

### C3 — "opción N" en un mensaje mixto no se resuelve como selección
"Voy a querer una vitamina C de la opción 9" llegó junto a otra pregunta de
precio. El extractor concatenó: **"macrodantina querer vitamina opción"**.
La resolución de "opción N" (elegir de last_options) debe tener PRIORIDAD
absoluta cuando el mensaje contiene "opción/de la opción N" Y hay
last_options activo: es una compra confirmada, no una búsqueda nueva.

### C4 — Contradicción "No tengo X" + lista de resultados (prompt, no matching)
En el caso 4 el matching funcionó BIEN (SOLUNOVAR por typo de 1 edición, PINVEX
directo). El error es de redacción: la instrucción de herramientas permite
abrir con "No tengo X" cuando el EXACTO no está aunque se presenten
alternativas inmediatamente después. La regla debe ser: si hay alternativas,
el mensaje abre con ellas ("Lo más parecido que tengo es…"); el "no tengo X
exacto" solo se dice si NO hay nada que ofrecer.

## Qué mejorar (plan F14, en orden de impacto)

1. **C1:** usar `_limpiar_transcripcion`/`_MULETILLAS_HABLA` también en texto
   escrito (`_extraer_termino_medicamento`), y añadir los apelativos que faltan
   ("mi amor", "mi vida", "corazón" ya está, "mi reyna", "camarada", etc.).
2. **C3:** resolver "opción N" ANTES de extraer término: si el turno menciona
   "opción N" y hay `last_options`, consumir la selección y no buscar.
3. **C4:** prompt + instrucciones de `buscar_medicamento`: prohibido
   "no tengo X" seguido de resultados; reformular apertura.
4. **C2 + pregunta del dueño (tabla de alias):** SÍ vale la pena, pero NO una
   tabla manual gigante. Propongo alias DATA-DRIVEN:
   - Tabla `med_aliases` (o JSON) poblada del log real `med_queries`: toda
     consulta sin resultados que un humano/handoff resolvió a un producto real
     se convierte en par alias→canónico.
   - Semilla inicial pequeña y curada (~30-50 entradas de Venezuela: typos
     frecuentes, nombres comerciales locales).
   - En runtime: alias exacto → reescribe el término ANTES de buscar (sin
     fuzzy); el fuzzy de 2 ediciones queda como ÚLTIMO recurso y NUNCA cruza
     si el alias existe.
5. **Multi-medicamento:** "nitrofurantoina de 50mg Y la vitamina C" = 2
   consultas. Dividir por conectores ("y", "también", coma) cuando ambos lados
   tienen token de fármaco.

## Resultados crudos de las simulaciones

Extraídos por el código ACTUAL (`_extraer_termino_medicamento` + `es_relevante`):

| Entrada del cliente | Término extraído | Efecto |
|---|---|---|
| "Buenas tardes!! Mi amor que precio tiene la nitrofurantoina de 50mg y la vitamina C" | `amor nitrofurantoina 50mg vitamina` | matchea TE AMO PRESERV ✓(bug), VITAMINA K, VITAMINA C, NITROFURANTOINA |
| "vivacina" | `vivacina` | matchea VITAMINA K y VITAMINA C (distancia 2) |
| "Precio de la macrodantina?? Voy a querer una vitamina C de la opción 9" | `macrodantina querer vitamina opción` | no resuelve opción 9; tokens basura |
| "…precio de solunoval solución bucal y pinvex solución bucal" | `solunoval solución bucal pinvex solución bucal` | matching OK (SOLUNOVAR ✓, PINVEX ✓) — el fallo fue solo de redacción |

## Prompt de continuidad (nueva sesión)

Ver `docs/F14-PROMPT-CONTINUIDAD.md`.
