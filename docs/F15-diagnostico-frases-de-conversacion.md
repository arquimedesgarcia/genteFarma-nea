# F15 — Diagnóstico: frases de conversación que se buscan como medicamento

**Estado:** diagnóstico medido, SIN implementar. Nada de esto se ejecutó ni se tocó en producción.
**Origen:** quejas del cliente (oct-2026), verbatim:

> - **«No puede ser Indu.»** — el usuario expresa que el laboratorio del medicamento no puede
>   ser Indu (o de la India); no es una petición de medicamento.
> - **«Vivo en Ciudad Bolivar.»** — el usuario indica dónde vive y el agente intentó buscar
>   *Bolivar* como medicamento, igual que *Vivo* y *Ciudad*.
> - **«Solo una marca?»** — pregunta por la marca (asumible: el laboratorio) del medicamento.
> - **«Por ahroa no»** — el agente asumió que «ahora» era un medicamento e intentó buscarla.

**Pregunta del usuario (a responder aquí):** ¿vale la pena investigar cómo hacer que el agente
**entienda primero la conversación** y ubique dónde está la pregunta de medicamento, en vez de
buscar cualquier frase como si fuera un fármaco?

**Respuesta corta:** sí, y el diagnóstico cambia el sitio del fix: no es "más frases en la
lista negra", es **de dónde sale la decisión de buscar**. Hoy esa decisión se toma por la
*forma* del texto, no por *evidencia de fármaco*.

---

## 1. Qué se midió (todo ejecutado sobre el árbol `a07f322`, local)

Arnés de funciones (`_extraer_termino_medicamento`, `hay_senal_de_farmaco`, `_parece_*`):

| Frase | término que se buscaría | `hay_senal_de_farmaco` | `_parece_consulta_medicamento` | `_parece_nombre_producto` |
|---|---|---|---|---|
| `No puede ser Indu.` | `ser indu` | **True** (`tokens_farmaco=['indu']`) | False | False |
| `Vivo en Ciudad Bolivar.` | `vivo ciudad bolivar` | **True** | **True** | **True** |
| `Solo una marca?` | `marca` | **True** | False | False |
| `Por ahroa no` | `ahroa` | **True** | False | False |
| `Vivo en Ciudad` | `vivo ciudad` | False | **True** | **True** |

Dos hechos incómodos:

1. **El extractor SIEMPRE devuelve un término.** `_extraer_termino_medicamento` quita verbos,
   relleno, apelativos, categorías terapéuticas y vías de administración; lo que quede, si
   tiene ≥3 letras, es "término". `'ser indu'`, `'marca'`, `'ahroa'`, `'vivo ciudad bolivar'`.
2. **La "señal de fármaco" no discrimina.** `hay_senal_de_farmaco` devolvió **True en 4 de las
   5 frases** — porque `tokens_farmaco` es, en la práctica, «cualquier palabra de ≥4 letras que
   no sea verbo de consulta». `'indu'` cuenta como fármaco. Esa bandera es la que después
   habilita la búsqueda, así que la puerta está abierta de par en par.

Y la puerta concreta que sí decide buscar está localizada: `_parece_nombre_producto`
(`app/turn.py`, ~4899) acepta **cualquier oración** que (a) no lleve `?`, (b) tenga ≤4 palabras,
(c) no contenga saludo/relleno conocido y (d) tenga una palabra de ≥5 letras. «Vivo en Ciudad
Bolivar.» cumple las cuatro: sin signo de pregunta, 4 palabras, ninguna en la lista de saludos,
y `ciudad`/`bolivar` tienen ≥5 letras ⇒ **True** ⇒ `_parece_consulta_medicamento` ⇒ **True** ⇒
se busca. El adjetivo "deliberadamente estrecho" del docstring describe el caso que se quiso
evitar («2 cajas», «que tal»), no este.

## 2. Reproducción end-to-end (no es teoría)

Con el simulador de conversaciones (`eval/f14-busqueda/simular_conversaciones.py`, escenario
`12-frases-que-no-son-medicamento`), la frase «Vivo en Ciudad Bolivar.» produjo **13 consultas
al catálogo** en un solo turno:

```
vivo ciudad bolivar → vivo → vivo ciudad oblivar → vivo ciudad bloivar → vivo ciudad boilvar
→ vivo ciudad bolviar → vivo ciudad boliavr → vivo ciudad bolivra → vivo ciudad volivar
→ boliva → boliv → boli → bol
```

Es decir: la frase de ubicación entra al buscador, y el **cascada de recuperación** del árbol
(transposiciones + truncamientos progresivos) la convierte en `bol`, `boli`, `boliv`… El
cliente ve «no tengo Bolivar» y el log `med_queries` se llena de basura que después contamina
el catálogo de typos y los alias derivados (F14.4). **El daño no es solo la respuesta mala: es
la contaminación del aprendizaje.**

Contra-caso medido (escenario `13-frases-con-contexto`): las MISMAS frases **en mitad de la
conversación** (después de listar un producto) **no dispararon ninguna consulta** — consultas
= `['macrodantina', 'macrodantina']`; las respuestas fueron conversacionales y correctas
(«¿Qué pasa con la macrodantina, el precio o algo más?», «Perfecto, aquí estoy cuando lo
necesites 👋»). El veneno está sobre todo en el mensaje **sin contexto previo**.

Límite honesto de esta medición: de las 4 quejas reproducí end-to-end **1** («Vivo en Ciudad
Bolivar.», el caso con cascada). En las otras 3 el *terreno* está medido (término basura +
bandera en True), y en producción el modelo del cliente sí las buscó, pero **no** las pude
reproducir con su modelo: este entorno corre LongCat y ellos pasaron el chat a DeepSeek v4.1
Flash (Ollama Cloud) en los últimos commits. Para cerrar el mapa hace falta correr los dos
escenarios con su modelo.

## 3. La tensión de fondo (por qué "más reglas" no alcanza)

El árbol tiene hoy una familia de filtros deterministas por frase/familia: `_parece_direccion`,
`_parece_referencia_sin_farmaco`, `_es_negativa_o_despedida`, `_es_reclamo_o_cortesia`,
`_es_solo_dosis_y_forma`, `_es_linea_descriptiva`, `_es_etiqueta_ocr`, `_SALUDOS_CONSULTA`…
y ninguno cubre las 4 quejas: `_parece_direccion('Vivo en Ciudad Bolivar.')` = **False**.

Pero el problema no es que falte la regla de "vivo en X". Es que compiten dos necesidades
legítimas:

- **«Shampo Dreene» debe buscar** (medido en su día: exigir verbo provocaba falsos negativos
  con nombres pelados).
- **«Vivo en Ciudad Bolivar» no debe buscar** (esta queja).

Ambas son "≤4 palabras, sin `?`, con palabra larga". Ninguna lista negra resuelve eso de
forma estable: cada queja nueva es una frase nueva. Lo que falta es **evidencia positiva de
que hay un fármaco** — y, cuando no la haya, **preguntar** en vez de buscar.

## 4. Opciones de diseño

| | Enfoque | Qué resuelve | Costo / riesgo |
|---|---|---|---|
| **A** | **Reglas por CLASE** (no por frase): preposición de lugar + topónimo (`vivo en`, `estoy en`, `soy de` + Ciudad/Estado), `ser/estar + nombre propio` (`no puede ser X`, `es de X`), pregunta de atributo sin fármaco (`una marca?`, `el laboratorio?`, `es original?`), dilatoria temporal (`por ahora no`, `después`, `mañana`) | las 4 quejas y sus primos | bajo; sigue siendo una lista, pero cada regla cubre una familia entera |
| **B** | **Evidencia positiva obligatoria para buscar**: el término debe traer al menos una prueba (token de fármaco conocido/afijo, dosis+unidad, forma farmacéutica, o coincidencia con el catálogo). Sin prueba ⇒ **no se busca: se pregunta** («¿me confirmas el nombre del medicamento?») | el caso general, incluidos los que aún no reportaron | medio; riesgo de falso negativo en typos sin evidencia (`vivacina`) — se mitiga con la regla "nombre pelado + verbo de consulta = buscar" y con preguntar en vez de negar |
| **C** | **Clasificador de intención antes de buscar** (mapa a {saludo, cortesía, dato personal, pregunta de atributo, dilatoria, consulta_de_medicamento}) con un LLM barato | el caso general, con menos reglas | alto: +1 llamada por turno (latencia y costo), y en F14 se midió que una prohibición extra en el chasis **desvía el estilo** en turnos sin catálogo |
| **D** | **A + B (recomendado)**: clases deterministas para las familias conocidas, y la regla de oro «**sin evidencia de fármaco no se busca: se pregunta**». C solo si A+B dejan un resto medible | todo lo anterior con coste controlado | bajo-medio; no toca la cadena de vetos ni `guards.py` |

**La decisión de producto que hay que tomar:** ¿preferimos *buscar de más* (molesta con
respuestas sobre palabras que no son medicamentos, contamina `med_queries`) o *buscar de menos*
(el cliente escribe un nombre raro y el agente pregunta en vez de negar)? La queja actual dice
que el segundo error se tolera mejor — es exactamente el «si no tiene la seguridad de cuál es
la pregunta real, que pregunte» que planteas.

## 5. Plan de evaluación (antes de tocar código)

1. **Corpus de no-consultas** (~40): las 4 quejas + variantes por clase (lugar, laboratorio,
   marca, dilatoria, cortesía, datos del paciente, reclamos) + las que ya cubre el árbol.
2. **Corpus de consultas legítimas** (~40): nombres reales del log `med_queries`, con typos
   (`vivacina`, `omeprasol`, `lorsatan`), con dosis, con forma, con marca, y nombres pelados
   (`Shampo Dreene`).
3. **Métrica**: por un lado consultas basura evitadas; por el otro **falsos negativos**:
   consultas legítimas que el agente deja de buscar. El objetivo no es 100/100 en el primero,
   es **cero falsos negativos** en el segundo (regla: ante duda, preguntar).
4. **Tres niveles**, como en F14: funciones (arnés determinista) → conversación (simulador,
   escenarios `12`/`13` + con su modelo) → Laboratorio (solo estilo; recordar: el Laboratorio
   local no tiene catálogo y oscila ±14).
5. Reproducir primero las 4 quejas **con el modelo del cliente** (DeepSeek v4.1 Flash) para
   tener el "antes" verdadero.

## 6. Restricciones (las mismas de F14)

- `app/guards.py` **intocable**; cadena de vetos en `turn.py` intacta.
- Cambios **aditivos**; nada de reescribir el flujo de turno.
- Push SOLO a `desarrollo` de `rsomoza01`/`gentefarma`; nunca a `main` ni al upstream.
- Simulaciones con modelo barato. NO usar Ollama local (GPU inestable).

## 7. Orden propuesto de implementación

- **F15.0** — reproducir las 4 quejas con el modelo del cliente (escenarios 12/13) y congelar el "antes".
- **F15.1** — reglas por clase (A) en la familia existente, con su test por clase.
- **F15.2** — evidencia positiva (**B**): la búsqueda exige prueba de fármaco; sin prueba, el turno pregunta (reusa el camino de "nombre poco claro" que ya existe).
- **F15.3** — medición de los dos corpus + reporte antes/después y decisión sobre C.
- **F15.4** — (opcional, según F15.3) clasificador de intención, solo si queda un resto medible.

**Modelo propuesto** (skill `nous-model-cost-selection`): `deepseek/deepseek-v4.1-flash` para
F15.0–F15.3 (medición + reglas quirúrgicas, barato con caché); si F15.4 (clasificador de
intención) se aprueba, ahí sí conviene subir a `z-ai/glm-5.3-flash` o pro y decidirlo aparte.
Pendiente: confirmación del usuario antes de ejecutar.
