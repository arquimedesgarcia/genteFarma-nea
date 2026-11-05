# F15.1 — Autorización de búsqueda POR TÉRMINO (cierre del PENDIENTE #1 de F15)

**Qué es:** el cambio que impide que el MODELO lance búsquedas con términos que el cliente no pidió
(`vitamina`, `acabo`, `ustedes` tras «tienes vivacina?») y que esos resultados lleguen al cliente.

**Estado:** implementado y medido en el árbol `desarrollo`; spec en
`docs/SPEC-F15-1-autorizacion-por-termino.md`. Base `be8d8ce` + docs (`3800475`).

**Restricciones respetadas:** `app/guards.py` **sin un solo cambio**, cadena de vetos de `turn.py`
intacta, cambios aditivos, nada tocado fuera del repo ni del entorno de desarrollo.

---

## 1. El hueco, medido antes de tocar código

Sonda determinista (sin modelo): `eval/f15-frases-conversacion/probe_autorizacion_por_termino.py`.

| Escenario | Árbol `be8d8ce` (antes) | Árbol con F15.1 |
|---|---|---|
| A) turno autorizado por el backstop con `vivacina` → el modelo busca `vitamina`, `acabo`, `ustedes` | **PASAN las 3** | las 3 rechazadas |
| B) turno autorizado por la capa con `losartan` → `vitamina`, `acabo` | **PASAN las 2** | las 2 rechazadas |
| C) el backstop NEGÓ `estafa` → el modelo la busca | **PASA** | rechazada |
| D) `sugerir_generico('vitamina')` sin autorización (segunda puerta) | **consulta el catálogo** | no consulta |
| **TOTAL** | **6 huecos** | **0 huecos** (17 pruebas con modelo real) |

Dos causas, en `app/tools.py`:

1. `_autorizar_busqueda` decidía por **turno**: `if self.intent_fuente != "llm": return None`
   (backstop decidido ⇒ autorizado todo lo que viniera después) e `intent_autorizado` se reutilizaba
   para cualquier término distinto.
2. **Segunda puerta sin candado** (hallazgo nuevo de esta fase): `_sugerir_generico` llamaba
   `crm.get_products(q=nombre)` sin pasar por la autorización central.

## 2. Qué se cambió

### 2.a La puerta (spec §3, R1-R7)

| Regla | Implementación |
|---|---|
| Cada término distinto pasa por la capa | `_autorizar_busqueda` guarda los términos aprobados del turno (`intent_terminos_autorizados`) y **no** los extiende a términos nuevos |
| El mismo término (normalizado) no paga llamada | `_clave_termino` (minúsculas, sin tildes, sin espacios repetidos) |
| El mismo producto con otro formato tampoco | `_mismo_producto` (tokens: `losartan 50 mg` ⊃ `losartan 50`) |
| El veredicto del backstop se hereda **solo para su término** | Si aprobó, autoriza ese término; si **negó**, el modelo no lo rescata (`estafa`) |
| El atajo por dosis/forma solo abre la **primera** búsqueda | `_tiene_evidencia_de_producto` ya no aplica con el turno ya usado |
| Los rechazos conclusivos se cachean | `intent_rechazos`: insistir no cuesta otra llamada ni duplica auditoría |
| Fail-closed intacto | `_rechazar_por_fallo_comprension` se conserva; los 2 tests de F15 siguen verdes |
| Segunda puerta cerrada | `_sugerir_generico` llama a la puerta antes de consultar el catálogo |
| Sin léxico nuevo | Nada de listas de palabras: decide la capa |

### 2.b Los dos huecos que destapó el Laboratorio (R9 y R10)

La primera corrida del Laboratorio con el árbol F15.1 (score 73, `run_wvp5ulsexf95fd7t1k2f`) dejó en
`med_queries`/`intent_decisions` términos que el cliente **no** había pedido pero que la puerta
autorizó: `oiga` (de «oiga y que me cuesta la fexofenasina?»), `firma`, `medica` y
`maria fernandez cmp 45231` (datos del paciente que el OCR de la receta pone delante del modelo).

Dos causas distintas, las dos cerradas:

- **R9 — la capa respondía por el MENSAJE, no por el CANDIDATO.** El mensaje sí traía una consulta
  (fexofenasina, una receta con tres medicamentos) y ese «sí» autorizaba el término que el modelo
  eligió. Ahora la puerta pregunta explícitamente por el candidato
  (`entender(..., candidato_obligatorio=True)` + «PREGUNTA ESTRICTA» en el contexto y en el prompt
  de la capa): «el veredicto es sobre ESTE término».
- **R10 — el atajo por número.** `_tiene_evidencia_de_producto` daba por buena cualquier cifra de 2+
  dígitos: `maria fernandez cmp 45231` (nombre + colegiatura) se autorizaba **sin pasar por la capa**.
  Ahora la cifra suelta solo cuenta como dosis si el término tiene ≤3 tokens y la cifra 2-4 dígitos
  (una cédula o un colegiado tienen 5+).

Archivos: `app/tools.py` (puerta, helpers, estado del turno, atajo), `app/intencion.py` (contrato
`candidato_obligatorio` + reglas del prompt), `tests/test_f15_intencion.py` (+12 tests).

## 3. Evidencia

| Nivel | Qué se corrió | Resultado |
|---|---|---|
| Compilación | `py_compile app/tools.py app/intencion.py` | OK |
| Tests | `pytest tests/ -q` | **166 verdes** (154 antes; 12 nuevos) |
| Sonda (puerta) | `probe_autorizacion_por_termino.py` | **0 huecos** (antes: 6) |
| Sonda (capa real) | idem `--model deepseek/deepseek-v4.1-flash`, 2 pasadas | **17/17 en ambas**: rechaza `vitamina`, `acabo`, `ustedes`, `estafa`, `oiga`, `firma`, `maria fernandez cmp 45231`; aprueba `losartan 50 mg`, `LOSARTAN 50`, **dos medicamentos** en el turno, **el genérico del producto mostrado** (`depomedrol` → `metilprednisolona`) y la **variante mal escrita** del pedido (`fexofenasina` → `fexofenadina`) |
| Corpus (no regresión) | 50 frases, modelo real | **0 falsos positivos, 0 falsos negativos**; 1 inconclusivo (`JSON inválido` del modelo en la misma frase que ya salía inconclusa en el baseline pre-cambio) |
| Camino REAL | `POST /chat`, 4 escenarios (`camino-real-f151.sh`) | 0 términos basura; 10 filas en `intent_decisions` y 12 en `med_queries`, **todas atribuibles** (`fuente`+`motivo`); «solo una marca? no era indu» → 0 búsquedas |
| Camino REAL (repeticiones) | «tienen vivacina?» ×4 con cada imagen (vieja `prefix151` vs nueva) | ambas: `vivacina` + variantes (`vibracina`, `vivicina`) aprobadas por la capa, **0 basura**; el modelo no intentó genéricos en ninguno de los 8 turnos |
| Laboratorio | 2 corridas con DB desechable fresca, juez `meituan/longcat-2.0` (gratis) | ver §3.1 |

### 3.1 Laboratorio

| Corrida | Árbol | Score | Verdes / rojos | Atribución |
|---|---|---|---|---|
| `run_wvp5ulsexf95fd7t1k2f` | F15.1 inicial (sin R9/R10) | 73 | 8 / 3 | `fuera_de_kb` y `receta_foto` = **del cliente** (los dos del informe F15); `pide_humano` = **del modelo/juez**: el agente SÍ hizo el handoff (`POST /api/bot/handoff` 200, reason «pidió humano» a las 19:14:58) y el juez leyó «ya avisé al equipo» como afirmación falsa. **No hay búsqueda involucrada**: la rama de handoff no la toca este cambio |
| `run_2j677cvumjmm7an8pqn2` | F15.1 final (R1-R10) | 73 | 8 / 3 | `fuera_de_kb` y `receta_foto` = **del cliente** (reproducen igual); `comprador_decidido` = **del modelo**: responde «Listo, quedó registrado» a «finaliza mi pedido» con el carrito VACÍO y **sin llamar a `finalizar_pedido`** (no hay una sola línea de esa herramienta en el log de la corrida). Candidato a veto nuevo tipo G13 (afirmar una acción sin tool call). `pide_humano` pasó a **verde** en esta corrida |

Evidencia de la capa en la corrida final (auditoría `intent_decisions` / `med_queries`, 47 y 26 filas):

- **Rechazados** (lo que antes entraba al catálogo): `2 economica`, `carrito hasta ahora`, `pensar`,
  `oigan`, `colmo`, `pregunta`, `receta`, `medica`, `maria fernandez cmp 45231`, `firma`,
  `fecha 30 08 2026`, `tomar 1 ayunas 20 dias`, `compre pastillas sirvieron puedo devolverlas`,
  `estafa`, `ladrones`…
- **Buscados** (nombres de medicamento, 0 basura): `losartan 50 mg`, `Daflon`/`daflon 500`,
  `diosmina hesperidina` (genérico de Daflon), `Esoz`/`esomeprazol`, `fexofenadina` (typo de
  «fexofenasina»), `panadol`, `paracetamol` (marca → principio activo), `acetaminofen`.
- **Sin falsos negativos** en los flujos legítimos: marca → principio activo, genérico pedido,
  variante mal escrita, dos medicamentos y el producto ya mostrado siguen aprobándose.

La banda de oscilación del Laboratorio es **±14** entre corridas idénticas (banda documentada en
fases anteriores), así que 73 vs el 82 de referencia no se atribuye al cambio salvo por los rojos,
que van uno por uno: los dos rojos del cliente se reproducen como en el informe F15 y el tercero
cambia de caso entre corridas (`pide_humano` en una, `comprador_decidido` en la otra), señal de
oscilación del modelo/juez y no de la capa de comprensión.

### 3.2 Lo que el camino real NO prueba (dicho claro)

El hueco original es **no determinista**: depende de que el modelo decida buscar un segundo término.
En los 8 turnos medidos no lo intentó en ninguna de las dos imágenes, así que esa diferencia
vieja/nueva no se observó en vivo; las pruebas del cierre son deterministas (sonda + tests) y la
corrida del Laboratorio, donde el hueco **sí** apareció (`oiga`, `firma`, `maria fernandez cmp 45231`,
`medica`). Lo que sí se verificó en vivo es que la puerta **no rompe** flujos legítimos: correcciones
del mismo nombre (`vibracina`), dos medicamentos en un turno, reintentos internos
(`'losartan 50 mg' sin resultados — reintento con 'losartan 50'`) y el genérico del producto mostrado.

## 4. Riesgos (y cómo quedaron contenidos)

| Riesgo | Estado |
|---|---|
| Falso negativo: consulta legítima tratada como charla | Medido: corpus 0 FP / 0 FN y sonda E/F/H en verde (categorías, síntomas, variantes mal escritas y producto mostrado siguen aprobándose) |
| Multi-medicamento (`losartan y metformin`) | Probado en la sonda y en el camino real: ambos términos aprobados |
| Coste: una llamada por término nuevo | Acotado por el tope de rondas; el mismo término/producto y los rechazos ya vistos no pagan |
| Romper las recuperaciones por catálogo (F14) | Solo el término que el modelo pasa entra por la puerta; alias, typos, núcleo y principio activo siguen dentro de la búsqueda autorizada |
| Proveedor de la capa lento/caído | Circuito de corte + fail-closed ya existentes: se pregunta en vez de buscar |

## 5. Observaciones para la siguiente sesión

- **Contrato de la capa con términos rechazados**: con `deepseek-v4.1-flash` la capa a veces devuelve
  `acto=consulta_medicamento` con `hay_consulta=false`, que `_veredicto_desde_json` considera
  incoherente ⇒ `fail-safe`: el término se rechaza igual, pero sin veredicto conclusivo (no se cachea
  y la fila queda como fail-safe). Ajustar el prompt para que un rechazo use otro `acto` mejoraría la
  **auditoría**, no la seguridad.
- **Foto de receta (OCR)**: el caso `receta_foto` sigue rojo por el lado del cliente (el agente afirma
  «ya vi la receta»), pero además el OCR mete en el turno texto que no es medicamento (nombre del
  paciente, colegiatura). R10 lo corta en la puerta; conviene revisar también qué texto se le pasa al
  modelo.
- La rama del codificador `gentefarma/fix/f15-term-scoped-search` implementaba la misma idea pero
  **rompía el fail-closed** (borraba `_rechazar_por_fallo_comprension` y seguía llamándolo: 2 tests
  rojos) y no cubría `sugerir_generico`. No se mergeó; se recuperó su idea y sus casos de prueba.
- El ciclo de medición de esta fase está automatizado en dos scripts de `eval/`:
  `camino-real-f151.sh` (escenarios) y `camino-real-reps.sh` (repeticiones), con DB desechable fresca
  por corrida y **sin tocar** el volumen del cliente.
