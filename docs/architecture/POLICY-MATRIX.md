# NEA — Matriz de políticas (TO-BE)

> **Paso 3.** Política determinista como **actor × acción × recurso × farmacia ×
> precondición × auditoría**. Formaliza, sin duplicar, lo que hoy decide
> `_autorizar_busqueda` (F15.1), la allowlist, la X-API-Key y la condición de las
> guardas. Acompaña a [`TO-BE.md`](TO-BE.md) y [`USE-CASES.md`](USE-CASES.md).
> **No modifica runtime.** **🔸 PENDIENTE** = decisión de producto.

---

## 1. Principios de la política

1. **Determinista y en backend.** La política decide; el LLM no concede permisos
   ([ADR-0002](ADR/ADR-0002-llm-sin-autoridad.md)).
2. **Puerta única para búsqueda de catálogo.** El Policy Engine **delega** la
   autorización por término en `tools._autorizar_busqueda:2768` (F15/F15.1); **no
   crea una segunda puerta** ([ADR-0003](ADR/ADR-0003-puerta-unica-autorizacion.md)).
3. **Fail-closed.** Si la comprensión falla, se deniega (`_rechazo_comprension`).
4. **Tenant validado por backend.** El `providerId` viene del contexto CRM, nunca
   del LLM ni del texto del mensaje (PLAN §7).
5. **Mínimo privilegio.** Un cliente no invoca acciones Staff; un empleado (futuro)
   no opera fuera de su farmacia/rol (PLAN §9).
6. **Las guardas no autorizan** ([ADR-0004](ADR/ADR-0004-guards-ultima-linea.md)).

---

## 2. Matriz principal (estado actual mapeado)

Columnas: **Actor** · **Acción** · **Recurso** · **Alcance de farmacia** ·
**Precondición / autorización** · **Auditoría**.

| Actor | Acción | Recurso | Farmacia | Precondición / autorización (AS-IS) | Auditoría |
|---|---|---|---|---|---|
| Cliente | Buscar catálogo (UC-01) | Catálogo CRM | `providerId` del contexto | `aiEnabled`+`windowOpen`+allowlist; **F15.1** `_autorizar_busqueda` por término; fail-closed | `intent_decisions`, `med_queries` |
| Cliente | Ver detalle/precio (UC-02) | Catálogo (lectura) | `providerId` | producto ya mostrado; precio solo del catálogo | — (lectura) |
| Cliente | Ver disponibilidad (UC-03) | Catálogo (lectura) | `providerId` | producto ya mostrado | — |
| Cliente | Agregar/actualizar carrito (UC-04) | `bot_cart` | por `conversation_id` | opción/SKU resuelto contra `last_options`; precio del catálogo | `bot_cart`, `bot_conversation` |
| Cliente | Preparar pedido / resumen (UC-05) | `bot_cart`+entrega | `conversation_id` | carrito no vacío; **no sale sin método de entrega** | `bot_conversation` (`delivery_*`) |
| Cliente | Confirmar pedido (UC-06) | ficha CRM + `bot_cart` | `providerId`+`conversation_id` | carrito no vacío + **confirmación explícita** | nota de ficha CRM |
| Cliente | Pedir humano (UC-08) | handoff CRM | `providerId` | determinista (G9 / `_pide_hablar_con_humano`) | `handoff_reason` |
| Cliente | Consulta clínica (UC-08) | handoff CRM | `providerId` | **fail-closed**: derivar, no aconsejar | motivo mínimo (🔸) |
| Sistema | Seguimiento (UC-07) | conversación | `conversation_id` | pedido abierto + franja/días + IA activa | `bot_conversation` (`followup_*`) |
| Sistema | Relay / Sender | CRM | — | best-effort, nunca descarta | `relay_queue`, `pending_send` |
| Staff (API key) | Leer analytics top-meds | `med_queries` | `providerId` (query) | `X-API-Key == CRM_BOT_API_KEY` | — |
| Staff (API key) | Leer pacientes crónicos | `patient_profiles` | `providerId` | `X-API-Key` | — |
| Staff | Marcar consent crónico | `patient_profiles` | `providerId` | **🔸 sin endpoint hoy** (`marcar_consent:831`) | PENDIENTE |
| Empleado/Farmacéutico/Admin | Operaciones internas | — | — | **🔸 PENDIENTE** (sin identidad/rol; PLAN §8 q3) | PENDIENTE |
| LLM | — | — | — | **ninguna**: no autoriza, no ejecuta, no afirma hechos | — |

---

## 3. Controles de acceso / canal (hoy)

| Control | Símbolo | Aplica a |
|---|---|---|
| Firma Meta `x-hub-signature-256` | `webhook.verify_signature:35-42` | `POST /webhook` (acepta sin secret en dev) |
| `X-API-Key == CRM_BOT_API_KEY` | `webhook.py:195-197,395-397,436-439` | `/chat`, `/analytics/*` |
| Allowlist `ALLOWED_WA_IDS` | `turn.py:288-293` | `run_turn` (se salta en lab) |
| Tester-only `/reset` | `turn.py:300-304` | `TESTER_WA_IDS` |

**⚠ Riesgo registrado (AS-IS §7.4):** dos rutas de ingesta con contratos distintos
(`/webhook` firmado vs. `/chat` por API-key) para el mismo `handle_flush`. El
Policy Engine debe tratar ambas con la misma política de actor/recurso.

---

## 4. Decisión de autorización como resultado tipado

El Policy Engine devuelve (sin reemplazar la puerta de catálogo):

- `Autorizado(accion, actor, recurso, farmacia)`
- `NoAutorizado(motivo)` — p. ej. fuera de allowlist, acción Staff pedida por Cliente.
- `RequiereAclaracion` — intención no concluyente (`hay_consulta=None`): **preguntar,
  no actuar**.
- Para búsqueda de catálogo: **delega** y propaga el veredicto de
  `_autorizar_busqueda` (`autorizado` / `rechazo_comprension`).

---

## 5. Pruebas de política (criterio de salida — para Pasos 5/9)

- **Positivas:** cada fila "Cliente" autoriza su acción con precondición cumplida.
- **Negativas (cross-tenant / cross-rol):**
  - Cliente **no** puede invocar acciones Staff/analytics.
  - Petición con `providerId` A no ve datos de `providerId` B.
  - Término no autorizado por F15.1 **no** llega al catálogo (paridad con
    `test_f15_intencion.py` A9).
  - `/chat` sin `X-API-Key` válida se rechaza.
- **Fail-closed:** comprensión caída → denegar, no buscar.

**🔸 PENDIENTE:** pruebas negativas de acceso cruzado Staff/empleado requieren el
modelo de identidad del Paso 9 (PLAN §8 q3).
