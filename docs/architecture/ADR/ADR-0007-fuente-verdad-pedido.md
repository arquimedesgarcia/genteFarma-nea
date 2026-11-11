# ADR-0007 — Fuente de verdad del pedido y separación preparar/confirmar

- **Estado:** Propuesta (diseño; una parte DEPENDE de decisión abierta)
- **Fecha:** 2026-11-10
- **Paso del plan:** 3 (prepara Paso 7)
- **Relacionada con:** [`../TO-BE.md`](../TO-BE.md) §5; [`../DOMAIN-MODEL.md`](../DOMAIN-MODEL.md) §4; [`../FLOW-ORDERS.md`](../FLOW-ORDERS.md); PLAN §7 "Pedidos", §8 preguntas 1, 2, 8

## Contexto

Hoy:
- El carrito vive en Postgres (`bot_cart`, `migrations/004`), con upsert atómico
  que **suma** cantidad (`db.cart_add:382-397`) y ventana de sesión
  `CART_SESSION_HOURS=12h`.
- "Finalizar pedido" **no crea una entidad pedido** en el CRM: registra una **nota
  de ficha** best-effort (`put_ficha` con `resultado=pedido`,
  `tools._finalizar_pedido:4700-4705`) y limpia el carrito (`cart_closed=True`).
- El estado del pedido se espeja en tres lugares (PG, `ToolRuntime`, `Conversation`
  en memoria) — DEPENDENCY-MAP R8.

**Decisiones abiertas (PLAN §8):** (1) ¿el CRM ofrece API de pedidos o solo
ficha/catálogo? (2) ¿existe pedido persistido en el CRM o solo carrito en NEA?
(8) ¿qué sistema es fuente de verdad de precio/disponibilidad?

## Decisión

Parte **diseñable ya** (no depende de la pregunta abierta):

1. **Separar `preparar pedido` de `confirmar pedido`** como estados explícitos
   (hoy están mezclados en el paso de resumen + confirmación "SI").
2. **Confirmación explícita obligatoria** antes de registrar algo irreversible
   (hoy ya existe vía `_es_confirmacion_resumen`, se formaliza como transición).
3. **El estado comunicado al cliente debe proceder del sistema fuente**; mientras
   no exista entidad de pedido en el CRM, NEA **no** afirma estados que no puede
   demostrar (se sostiene con G13).
4. **Identificador único por intento de pedido (idempotency key).** Cada *intento
   de confirmación* genera un `order_attempt_id` único (p. ej. UUID) en el momento
   en que el cliente confirma, **persistido** antes de llamar al sistema fuente.
   - **No** basta con `conversation_id` + hash del carrito: dos pedidos legítimos
     **distintos** con el mismo contenido (misma conversación, mismos ítems y
     cantidades en otro momento) colisionarían y el segundo se descartaría como
     "duplicado". El hash del carrito puede usarse como **dato de contexto/control
     de cambios**, nunca como clave de unicidad del intento.
   - El `order_attempt_id` protege frente a **reintentos** del mismo intento (doble
     webhook, timeout + retry, doble tap del cliente): la confirmación es
     **atómica** — se registra el intento con el id y una comprobación de
     existencia (p. ej. `INSERT … ON CONFLICT (order_attempt_id) DO NOTHING`),
     de modo que un reintento del **mismo** intento es inocuo y un intento
     **nuevo** (otro id) sí procede.
   - El resultado del sistema fuente se liga al `order_attempt_id` para poder
     reconciliar y no afirmar un registro que no se pueda demostrar (G13).

Parte **🔸 PENDIENTE (bloquea el modelo transaccional completo del Paso 7):** si el
pedido debe persistirse como entidad en el CRM, con estados
`confirmado/aceptado/preparado/entregado/cancelado`, y cuál es la fuente de verdad
de precio/disponibilidad al confirmar. **No se diseña la máquina de estados
extendida contra supuestos.**

## Alternativas consideradas

| Alternativa | Por qué se descarta / aplaza |
|---|---|
| Modelar ya el pedido completo con estados del CRM | Depende de preguntas abiertas 1/2/8; diseñar ahora es diseñar contra supuestos (PLAN §8). |
| Mantener "finalizar = nota de ficha" como estado final | Aceptable **temporalmente**; no permite seguimiento real de estado de pedido. Se marca como límite actual. |
| Idempotencia por mensaje únicamente (dedup actual) | El dedup de `processed_message` cubre el webhook, no la confirmación de pedido; se necesita clave a nivel de pedido. |

## Consecuencias

- **Positivas:** la separación preparar/confirmar y la idempotencia se pueden
  especificar y probar sin tocar el CRM.
- **Negativas:** hasta cerrar las preguntas 1/2/8, el "estado de pedido" real es
  solo carrito + nota; el roadmap del Paso 7 queda parcialmente bloqueado.
