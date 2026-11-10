# Evaluación de integración del autor original

**Estado:** PARCIAL — auditoría estática remota; integración y validación local pendientes.  
**Repositorio destino:** `arquimedesgarcia/genteFarma-nea`  
**Rama base verificada:** `agent-qa`  
**HEAD base:** `0f09e0a3f7fb60a0e49fbd4afa5d24b28e75bdbb`  
**Rama de este informe:** `fix/integracion-autor-auditoria`  
**Upstream:** `kevinrivm/nea-agent`  
**HEAD upstream/main:** `ad891389cc5402e35a9b2a3b4dcd15fda0a846d5`

## 1. Alcance y limitaciones

Se leyó el prompt `docs/PROMPT-CODIFICADOR-INTEGRAR-AUTOR-ORIGINAL.md` desde el HEAD real de `agent-qa` y se inspeccionaron los árboles, commits y archivos de ambos repositorios mediante GitHub.

**No se ejecutó un checkout local, pytest, py_compile, sondas, corpus con modelo real ni Laboratorio.** El entorno de ejecución disponible en esta sesión no contiene el clon `D:\Proyectos\GenteFarma\agentNEA`, Docker Desktop, el proxy local `:11500` ni sus credenciales. Tampoco está instalada la skill `vocero-nea-qa` (la lista de skills disponibles en esta sesión solo contiene Plugin Management).

Por tanto:
- Este documento es una curaduría estática de candidatos, no una validación funcional.
- Ningún cambio de código del autor se integra en esta pasada.
- No se declara PASS ni se atribuyen resultados de pruebas no ejecutadas.
- No se modificó `agent-qa`, `desarrollo`, `main`, `origin` ni `upstream`.

## 2. Línea base verificada

| Referencia | SHA | Resultado |
|---|---|---|
| `agent-qa` | `0f09e0a3f7fb60a0e49fbd4afa5d24b28e75bdbb` | HEAD real de la rama |
| Prompt de integración | blob `714eeae4083a505d93d5ac7a5b0e172a968ee97d` | Leído en ese HEAD |
| `upstream/main` | `ad891389cc5402e35a9b2a3b4dcd15fda0a846d5` | HEAD real consultado |
| Base histórica indicada para upstream | `249d05a78bc114fcef16e8ad8160abda362782ec` | Usada para comparar la evolución de upstream |

El prompt menciona `agent-qa` en `cee0092`, pero la rama avanzó tres commits hasta `0f09e0a`. La comparación `cee0092...0f09e0a` muestra:
- incorporación del propio prompt;
- actualización del corpus `eval/f15-frases-conversacion/corpus-deepseek_deepseek-v4.1-flash.json).

No se observan cambios de aplicación en esos tres commits.

La comparación dentro de upstream `249d05a...ad89138` devuelve **10 commits adelante, 0 atrás**. La API informa cambios en:
- `.github/workflows/imagen-dev.yml`;
- `CHANGELOG.md`;
- `CLAUDE.md`;
- `Dockerfile.deploy`;
- `app/ensayo.py` (nuevo);
- `app/main.py`;
- `app/multiorg.py`;
- `requirements.txt`;
- `tests/test_ensayo.py` (nuevo).

**Importante:** el punto `249d05a` se tomó como base histórica indicada por el contexto de trabajo y se comparó dentro del repositorio upstream. No se pudo demostrar un merge-base Git entre ambos repositorios mediante esta interfaz.

## 3. Inventario de ramas upstream

La API devolvió 50 ramas en upstream al momento de la consulta:

```
208-agenda-nea-recordatorios
209-nea-configuracion-guiada
arreglo-arranque-multiorg
arreglo-respuesta-cerebro
ci/dev-en-aisha
ci/imagen-ghcr
codex/arnes
dev
docs/cierre-1.0.0
docs/cierre-1.1.0
docs/release-1.0.0
feat/agenda-sin-ambiguedad
feat/blindaje-extraccion
feat/cierre-sin-rumbo
feat/modo-ensayo
feat/olvidar-conversacion
feat/webhook-url-secreta
feat/031-nea-por-despacho
feat/033-laboratorio-por-contrato
feat/034-roles-como-datos
feat/038-mover-etapa
fix/audit-hardening
fix/calendario-y-horas-libres
fix/cita-cancelada-sin-inventar
fix/cloud-media-route
fix/compatibilidad-agenda-vocero
fix/conflicto-409-anidado
fix/contexto-cita-cerebro
fix/dedup-por-mensaje
fix/fecha-solo-si-la-pide
fix/huecos-por-fecha
fix/lista-de-testers
fix/modelo-que-oye
fix/pypdf-6.21.4
fix/relay-modo-estandar
fix/texto-junto-a-herramientas
fix/turno-sin-crm-y-promesas
fix/turnos-serializados
fix/whatsapp-formato-candado-health
fix/zona-del-negocio
fix/zoom-reminder-confirmation
fix/032-seguimiento-permitidos
llm-proveedor-configurable
main
modo-cloud-vocero-multitenant
motivo-sin-credencial
multiorg-un-proceso-muchos-negocios
perf/velocidad-a-main
perf/velocidad-del-agente
readme-una-nea-por-negocio
```

Se compararon además diez ramas de interés contra `main`: `perf/velocidad-del-agente`, `perf/velocidad-a-main`, `feat/modo-ensayo`, `fix/pypdf-6.21.4`, `fix/audit-hardening`, `llm-proveedor-configurable`, `feat/blindaje-extraccion`, `fix/texto-junto-a-herramientas`, `fix/turno-sin-crm-y-promesas` y `fix/turnos-serializados`. Todas devuelven `ahead_by=0` frente a `main`: son ancestros/historial ya incorporado, no contienen commits nuevos por encima del HEAD actual de `main`.

No se hizo comparación individual de las otras 39 ramas; sus nombres quedan inventariados, pero no se certifica aquí que cada una esté totalmente integrada.

## 4. Tabla de decisión

| Commit/rama del autor | Qué hace | ¿Ya lo tenemos? | Decisión | Riesgo | Evidencia / motivo |
|---|---|---|---|---|---|
| `4f110da` — `perf/velocidad-del-agente` | Añade `LLM_REASONING_EFFORT`, `LLM_PROVIDER_SORT`, `extra_body` y reintento sin extras cuando el proveedor los rechaza; incorpora tests | No | **Adaptar, no integrar aún** | Medio/alto | El código de farmacia tiene `Settings` y `OpenAiLlm` propios; no existen esos parámetros en el constructor ni en la configuración inspeccionada. El ruteo `throughput` y `reasoning=minimal` deben ser opt-in y medirse con los modelos/proveedores reales usados por la farmacia. |
| `fb8bdf5` — `feat/modo-ensayo` | Endpoint `POST /vocero/ensayo` que simula conversaciones sin enviar WhatsApp ni persistir memoria | No | **Descartar para este despliegue** | Alto | `app/ensayo.py` depende de `crm_brains`, `dispatch`, `http_limits`, `multiorg`, ficha firmada del CRM y contrato de Vocero Cloud. La aplicación de farmacia inspeccionada es mono-farmacia y usa `provider_id`; copiar el endpoint no sería una integración aislada. |
| `4a473c7` / `fix/pypdf-6.21.4` | Actualiza pypdf 6.21.2 → 6.21.4; el commit upstream declara que corrige siete CVE | Parcial | **Adaptar como cambio de seguridad, pendiente de pruebas** | Medio | El `requirements.txt` de farmacia permite `pypdf>=5.1`, por lo que no expresa el mínimo corregido. Se debe confirmar compatibilidad, ejecutar `pip-audit`, tests de extracción PDF y fijar un mínimo/versión reproducible. No se cambió la dependencia sin poder probarla. |
| `5ffc420` / `8186fb8` — CI de imagen dev | Construye imagen de desarrollo y notifica Coolify de Aisha | No | **Descartar** | Bajo | Flujo de despliegue específico del entorno upstream; incluye nombres, secretos y destino Coolify ajenos al despliegue de farmacia. |
| `Dockerfile.deploy` | Imagen de despliegue para el flujo anterior | No | **Descartar** | Medio | No sustituye ni complementa automáticamente el Dockerfile y despliegue actuales. Requiere una decisión de infraestructura independiente. |
| Cambios de `CHANGELOG.md`, `CLAUDE.md` y documentación asociada | Documentación de Vocero Cloud/upstream | Parcial/no aplicable | **Descartar como portación de código** | Bajo | No aporta comportamiento ejecutable al agente farmacia; copiarla generaría documentación de otra arquitectura. |
| `app/main.py` y `app/multiorg.py` asociados a ensayo | Cableado del endpoint y resolución multi-organización | No | **Descartar junto con modo ensayo** | Alto | No se deben portar archivos completos ni introducir multi-organización como efecto colateral de una función de pruebas. |

## 5. Comprobación de solapamiento con el dominio farmacia

En el delta agregado de upstream desde `249d05a` hasta `ad89138` no aparecen cambios en:
- `app/tools.py`;
- `app/turn.py`;
- `app/guards.py`;
- `app/intencion.py`;
- `app/relevancia.py`.

Por tanto, ese delta no contiene una corrección nueva directa para F14, F15/F15.1, autorización de búsquedas, catálogo o guardas G1-G12. No se debe importar una refactorización del autor con la expectativa de que cierre esos problemas.

La rama `agent-qa` consultada conserva el enfoque mono-farmacia en `app/config.py` (`provider_id`) y el cliente LLM propio en `app/llm.py`. Su `requirements.txt` usa rangos amplios, incluido `pypdf>=5.1`.

## 6. Validación solicitada y estado real

| Validación | Estado | Motivo |
|---|---|---|
| Inventario de `upstream/main` | **HECHO** | HEAD y delta de 10 commits verificados |
| Inventario de ramas upstream | **PARCIAL** | 50 ramas listadas; 10 ramas de interés comparadas contra main |
| Filtrado estático de candidatos | **HECHO** | Tabla de decisión de cambios del delta |
| `py_compile app/*.py` | **NO EJECUTADO** | No hay checkout local del proyecto en esta sesión |
| `.venv-test/Scripts/python.exe -m pytest tests/ -q` | **NO EJECUTADO** | No hay entorno virtual ni dependencias del proyecto disponibles |
| Sondas F14/F15.1 | **NO EJECUTADAS** | Requieren checkout y skill/recetas locales |
| Corpus 50 frases con modelo real | **NO EJECUTADO** | Requiere proxy `:11500`, configuración y modelo |
| Laboratorio con DB desechable | **NO EJECUTADO** | No hay Docker Desktop, proxy ni credenciales |
| Integración de cambios de código | **NO REALIZADA** | No se debe integrar sin ejecutar validaciones posteriores a cada cambio |

El prompt original cita 174 tests verdes como base. Ese número no se ha vuelto a medir aquí. En el mismo repositorio existe un informe QA anterior que cita 166 tests para otra referencia (`desarrollo` en `5b7815e`); no son cifras intercambiables. Hay que ejecutar la suite sobre el HEAD exacto antes de aceptar el número de baseline.

## 7. Plan recomendado para completar la integración

1. En el entorno local descrito por el prompt, cargar la skill `vocero-nea-qa`, comprobar `git status -sb`, confirmar `agent-qa` y árbol limpio.
2. Medir y guardar baseline real: `py_compile`, pytest completo, sondas F14/F15.1 y corpus 50/50 con proxy validado.
3. Abrir una rama separada desde `agent-qa` para el cambio de seguridad `pypdf`; actualizar versión mínima/fijación según política de dependencias y ejecutar `pip-audit`, tests PDF y suite completa.
4. Evaluar la optimización LLM en otra rama, inicialmente con flags vacíos/desactivados; añadir tests de payload, rechazo del proveedor y reintento. Solo habilitarla mediante configuración explícita y corrida A/B pareada con los modelos reales de farmacia.
5. Mantener fuera el modo de ensayo upstream. Si se necesita un modo de pruebas, diseñarlo contra el contrato y aislamiento de la aplicación farmacia, sin importar la infraestructura multi-org de Vocero Cloud.
6. Después de cada cambio, ejecutar toda la batería requerida. No llevar nada a `agent-qa` hasta que compile, pasen tests, sondas y corpus.

## 8. Resumen ejecutivo

- Upstream `main` está en `ad89138`, diez commits después de la base histórica `249d05a`.
- Se inventariaron 50 ramas; diez ramas relevantes comparadas no están por delante de `main`.
- No hay cambios nuevos del autor en las piezas críticas de farmacia: `tools.py`, `turn.py`, `guards.py`, `intencion.py` o `relevancia.py`.
- El modo de ensayo se descarta: depende de multi-organización y del CRM Vocero Cloud.
- La optimización de velocidad queda como adaptación opcional, pendiente de A/B con modelos reales.
- La actualización de pypdf es la candidata de seguridad más clara, pero queda pendiente de `pip-audit` y pruebas.
- CI y Dockerfile de Coolify son específicos del entorno upstream y se descartan.
- No se modificó código de aplicación ni se tocó ningún remoto upstream.
- No se ejecutaron pruebas locales, sondas ni corpus; no se declara PASS.
- La integración queda **PARCIAL** hasta completar validación en el entorno local autorizado.
