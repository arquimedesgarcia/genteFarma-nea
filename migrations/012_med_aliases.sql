-- 012_med_aliases.sql — Alias de ESCRITURA de medicamentos (F14.4).
--
-- Qué hace: cuando el cliente escribe un medicamento con una grafía que se
-- CONOCE, el agente reescribe el término ANTES de consultar el catálogo y apaga
-- la tolerancia a typos de esa búsqueda. Así un término mal escrito no puede
-- saltar de categoría terapéutica por el fuzzy de 2 ediciones (caso real
-- medido: 'vivacina' → VITAMINA K y VITAMINA C).
--
-- REGLAS (ver app/aliases.py, docstring):
--   * Solo variantes ORTOGRÁFICAS del mismo nombre. NUNCA marca→principio
--     activo (eso es `_buscar_por_principio_activo` y una reescritura forzada
--     escondería el producto de marca si el catálogo lo tiene).
--   * Nada con final ambiguo (amlodipina/amlodipino, ciprofloxacina/-o):
--     la reescritura desactiva el fuzzy, así que una grafía canónica errada
--     devuelve CERO resultados. Fail-safe en tools.py: si el alias deja 0
--     productos, se reintenta con el término ORIGINAL y fuzzy.
--
-- Origen de la semilla:
--   'med_queries' → par typo→grafía usada después en la MISMA conversación
--                   (log real del 2026-09-29 en el entorno de QA).
--   'cliente'     → caso real verificado por simulación (docs/F14).
--   'codigo'      → typo medido en comentarios de app/relevancia.py y
--                   app/tools.py.
--
-- Idempotente: se re-ejecuta en cada arranque (ON CONFLICT DO NOTHING), así que
-- agregar pares nuevos NO sobrescribe los que el equipo ya haya ajustado.

CREATE TABLE IF NOT EXISTS med_aliases (
    alias      TEXT PRIMARY KEY,          -- grafía del cliente (normalizada)
    canonico   TEXT NOT NULL,             -- grafía que usa el catálogo
    origen     TEXT NOT NULL DEFAULT 'semilla',
    nota       TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_med_aliases_canonico ON med_aliases (canonico);

INSERT INTO med_aliases (alias, canonico, origen, nota) VALUES
    -- Caso real 4 de F14: el catálogo escribe SOLUNOVAR.
    ('solunoval',    'solunovar',    'cliente',    'docs/F14-diagnostico-busqueda.md (caso 4)'),
    -- med_queries (2026-09-29): primera consulta 'fexofenasina' sin resultados;
    -- la misma conversación siguió con la grafía correcta.
    ('fexofenasina', 'fexofenadina', 'med_queries', 'log real QA 2026-09-29'),
    -- Typos medidos en comentarios del código (relevancia.py / tools.py).
    ('omeprasol',    'omeprazol',    'codigo',     'relevancia.py: typo soportado'),
    ('diclofencao',  'diclofenaco',  'codigo',     'relevancia.py: typo soportado'),
    ('amoxicilna',   'amoxicilina',  'codigo',     'relevancia.py: medido 10 resultados'),
    ('shampo dreene','shampu drene', 'codigo',     'relevancia.py: medido'),
    -- Ortográficas venezolanas frecuentes, todas con grafía canónica
    -- inequívoca (misma terminación en español; sin ambigüedad -o/-a).
    ('amoxacilina',  'amoxicilina',  'semilla',    'vocal interna'),
    ('azitromisina', 'azitromicina', 'semilla',    's/x'),
    ('flucozanol',   'fluconazol',   'semilla',    'vocal interna'),
    ('ceftriasona',  'ceftriaxona',  'semilla',    's/x'),
    ('gentamisina',  'gentamicina',  'semilla',    's/c'),
    ('metmorfina',   'metformina',   'semilla',    'metátesis'),
    ('prednizona',   'prednisona',   'semilla',    'z/s'),
    ('clonacepan',   'clonazepam',   'semilla',    'p/n'),
    ('lozartan',     'losartan',     'semilla',    'z/s'),
    ('lorsatan',     'losartan',     'semilla',    'dos ediciones (la r se corre): el alias lo hace determinista, sin depender del fuzzy'),
    ('bitamina',     'vitamina',     'semilla',    'b/v (letra de vitamina: bitamina c)')
ON CONFLICT (alias) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Derivación DATA-DRIVEN desde el log de consultas (med_queries).
--
-- La tabla se mantiene viva con evidencia real: toda consulta SIN resultados
-- que en la MISMA conversación se resolvió después con otra grafía (con
-- resultados o agregada al carrito) es candidata a par typo→canónico. La
-- consulta de abajo lista los candidatos para revisión humana; el método
-- `PgStore.derivar_aliases()` (app/db.py) la ejecuta y devuelve las filas.
-- NO se auto-insertan: un alias apaga el fuzzy, así que un canónico errado
-- devuelve cero resultados (por eso el fail-safe de tools.py).
--
-- SELECT f.term AS alias, o.term AS canonico, count(*) AS veces
-- FROM med_queries f
-- JOIN med_queries o
--   ON o.conversation_id = f.conversation_id
--  AND o.created_at > f.created_at
--  AND o.created_at < f.created_at + interval '30 minutes'
--  AND (o.result_count > 0 OR o.added_to_cart)
-- WHERE f.result_count = 0
--   AND length(f.term) BETWEEN 5 AND 30
--   AND lower(f.term) <> lower(o.term)
-- GROUP BY f.term, o.term
-- ORDER BY veces DESC;
--
-- `med_queries` guarda el término tal como se buscó y, cuando hubo resultados,
-- el `product_name` del primer producto: esa es la evidencia de la grafía
-- canónica (columna adicional en el SELECT si se quiere el nombre del catálogo).
-- ---------------------------------------------------------------------------
