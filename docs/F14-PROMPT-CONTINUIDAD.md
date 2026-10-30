# F14 — Prompt de continuidad para nueva sesión

Contexto que la sesión nueva necesita (todo verificable en el repo):

```
Proyecto: agente NEA (D:\Proyectos\GenteFarma\agentNEA, rama desarrollo).
Remotos: `origin` = rsomoza01/nea-agent (push permitido SOLO a `desarrollo`,
JAMÁS a main), `gentefarma` = arquimedesgarcia/genteFarma-nea (fork nuestro),
`upstream` = kevinrivm/nea-agent (SOLO lectura; ojo: su main ELIMINÓ el flujo
de farmacia — no tomar árbol de ahí).

Trabajo previo: guardas anti-alucinación G1-G12 (app/guards.py + cadena de
vetos en app/turn.py) validadas en el Laboratorio (95/100, F13). No romperlas.

Tarea: implementar el spec `docs/F14-diagnostico-busqueda.md` (LÉELO PRIMERO).
Causas raíces ya verificadas por simulación con el código real:
1. Apelativos de cortesía ("mi amor") no se limpian en TEXTO ESCRITO — solo en
   transcripciones de voz (_MULETILLAS_HABLA en turn.py:3073, usada solo por
   _extraer_termino_transcripcion). "amor" validó "TE AMO PRESERV" (preservativo).
2. "opción N" en mensaje mixto ("Precio de la macrodantina?? voy a querer una
   vitamina C de la opción 9") no se resuelve como selección de last_options;
   extrajo "macrodantina querer vitamina opción".
3. Fuzzy de 2 ediciones cruza categorías: "vivacina"→VITAMINA (K y C).
4. Contradicción de redacción: "No tengo SOLUNOVAL BUCAL" + lista de resultados
   inmediata — el matching funcionó bien, el prompt lo redacta mal.
5. Multi-medicamento: "nitrofurantoina 50mg y la vitamina C" = 2 búsquedas,
   hoy se concatena en un término.

Implementación (prioridad):
F14.1 — limpiar apelativos/muletillas también en texto escrito.
F14.2 — resolver "opción N" ANTES de extraer término (si last_options activo).
F14.3 — prompt: prohibido "no tengo X" seguido de resultados; apertura con
        alternativas cuando las hay.
F14.4 — tabla de alias DATA-DRIVEN `med_aliases` (migración + carga al boot +
        reescritura del término pre-búsqueda): semilla curada pequeña
        (typos VE frecuentes) + par alias→canónico derivado del log
        `med_queries` (consultas sin resultados resueltas luego). El fuzzy de
        2 ediciones queda como último recurso y no se aplica si el alias existe.
F14.5 — dividir términos por conectores cuando ambos lados tienen token de
        fármaco (2 búsquedas, no 1 concatenada).

Validación (3 niveles + Laboratorio):
1. python -m py_compile app/*.py en host (o .venv-test).
2. pytest: los 462 tests del árbol deben seguir 459+ (3 rojos conocidos
   G4-vs-strikes, NO tocar). Añadir tests unitarios de extracción con los 4
   casos reales de F14 como regression.
3. docker compose build nea + import en contenedor +
   `docker exec vocerocrm-nea-1 python -c "from app import turn"`.
4. Laboratorio de voceroCRM (ver skill vocero-nea-qa): 2 corridas, juez
   LongCat vía proxy Nous :11500 (NO Ollama: la GPU local es inestable),
   estado fresco (TRUNCATE nea-db pidiendo autorización), delta < 8 para PASS.

Restricciones permanentes:
- Push SOLO a `desarrollo` de rsomoza01 (o a gentefarma); JAMÁS a main de
  nadie ni a upstream.
- Cambios aditivos; no romper vetos G1-G12 ni plantillas de guards.py.
- Antes de ejecutar agentes de código: el spec ya está en docs/F14-*.md;
  commitear los docs.
- Simulaciones con modelo gratuito o de bajo costo (skill
  nous-model-cost-selection); no es tarea compleja.
- Entregar al final: reporte en eval/ o docs/ con los 4 casos antes/después
  y los runIds del Laboratorio.
```
