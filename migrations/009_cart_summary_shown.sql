-- 009_cart_summary_shown.sql — marca cuándo se mostró el Resumen del Pedido.
-- Idempotente: se re-ejecuta en cada arranque (Constitución III).
--
-- Propósito: tras mostrar el Resumen del Pedido (ver_carrito), ese pedido queda
-- "cerrado" para acumular más ítems. La siguiente consulta de medicamento
-- (buscar_medicamento) arranca un carrito nuevo: no suma al del resumen anterior,
-- aunque esté dentro de la ventana de sesión (CART_SESSION_HOURS).

ALTER TABLE bot_conversation
  ADD COLUMN IF NOT EXISTS cart_summary_shown BOOLEAN NOT NULL DEFAULT FALSE;
