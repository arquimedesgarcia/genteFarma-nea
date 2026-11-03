"""F15 — regresiones de la capa de comprensión del acto de conversación.

Cubre: caminos rápidos, contrato JSON (incluido lo roto), fail-safe (timeout,
proveedor caído, JSON inválido, capa apagada), las 4 quejas reales y la
auditoría en `med_queries`. Ningún test llama a un LLM real: se inyecta un
`FakeLlm` con la respuesta (o el fallo) que se quiere medir.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.intencion import (
    ACTOS,
    Entendimiento,
    _extraer_json,
    _veredicto_desde_json,
    camino_rapido,
    entender,
)
from app.state import MemoryStore

RAIZ = Path(__file__).resolve().parents[1]


class FakeLlm:
    """LLM de mentira: devuelve `contenido`, lanza `error` o duerme `demora`."""

    def __init__(self, contenido: str | None = None, error: Exception | None = None,
                 demora: float = 0.0) -> None:
        self.contenido = contenido
        self.error = error
        self.demora = demora
        self.llamadas = 0
        self.ultimos_mensajes: list[dict] = []

    async def complete(self, messages, tools=None):  # noqa: ANN001
        self.llamadas += 1
        self.ultimos_mensajes = messages
        if self.demora:
            await asyncio.sleep(self.demora)
        if self.error:
            raise self.error

        class _R:
            content = self.contenido

        return _R()


class Settings:
    """Settings mínimos para la capa."""

    def __init__(self, **kw):
        self.intent_layer = True
        self.intent_model = ""
        self.intent_api_key = ""
        self.intent_base_url = ""
        self.intent_timeout = 12.0
        self.openai_api_key = "x"
        self.openai_base_url = ""
        for k, v in kw.items():
            setattr(self, k, v)


def _veredicto(acto: str, hay: bool, termino: str | None = None,
               confianza: float = 0.9) -> str:
    return json.dumps(
        {"acto": acto, "hay_consulta": hay, "termino": termino,
         "confianza": confianza, "motivo": "test"}
    )


# --------------------------------------------------------------- caminos rápidos ---

class TestCaminoRapido:
    def test_sin_termino_candidato_no_hay_camino_rapido(self):
        assert camino_rapido("tienes algo para la gripe?", None) is None

    @pytest.mark.parametrize("texto,candidato", [
        ("vivacina", "vivacina"),
        ("shampo dreene", "shampo dreene"),
        ("omeprasol", "omeprasol"),
        ("atamel 500", "atamel 500"),
    ])
    def test_nombre_pelado_corto_busca(self, texto, candidato):
        ent = camino_rapido(texto, candidato)
        assert ent is not None
        assert ent.hay_consulta is True
        assert ent.fuente == "nombre"

    @pytest.mark.parametrize("texto,candidato", [
        # Las 4 quejas reales.
        ("No puede ser Indu.", "ser indu"),
        ("Vivo en Ciudad Bolivar.", "vivo ciudad bolivar"),
        ("Solo una marca?", "marca"),
        ("Por ahroa no", "ahroa"),
        # Falsos positivos que destapó la sonda con el extractor real: llevan VERBO
        # de consulta pero son charla. Retirar el camino rápido por verbo los evita.
        ("Solo una marca o hay varias?", "marca varias"),
        ("Por ahora no necesito nada", "ahora"),
        ("tienen delivery?", "delivery"),
        ("aceptan zelle?", "aceptan zelle"),
        ("a que hora cierran hoy?", "hora cierran hoy"),
        ("gracias, linda", None),
        ("hola mi amor buenos dias", None),
    ])
    def test_charla_no_se_resuelve_con_heuristica(self, texto, candidato):
        """Ni por forma ni por verbo: estas frases las juzga la capa."""
        assert camino_rapido(texto, candidato) is None

    def test_el_verbo_de_consulta_ya_no_decide_solo(self):
        """Regresión del fallo medido: 'tienen delivery?' disparaba búsqueda."""
        from app.turn import _extraer_termino_medicamento

        for frase in ("tienen delivery?", "aceptan zelle?", "por ahora no necesito nada"):
            candidato = _extraer_termino_medicamento(frase)
            assert camino_rapido(frase, candidato) is None, frase


# --------------------------------------------------------------------- contrato ---

class TestContratoJson:
    def test_tolera_cercas_de_markdown(self):
        texto = 'ok\n```json\n{"acto": "saludo", "hay_consulta": false}\n```'
        assert _extraer_json(texto) == {"acto": "saludo", "hay_consulta": False}

    def test_tolera_prologo_y_cola(self):
        datos = _extraer_json('Claro: {"acto":"otro","hay_consulta":false} fin')
        assert datos == {"acto": "otro", "hay_consulta": False}

    def test_llaves_dentro_de_cadena_no_confunden(self):
        datos = _extraer_json('{"motivo":"dice { que no }","acto":"otro"}')
        assert datos is not None and datos["motivo"] == "dice { que no }"

    def test_json_roto_devuelve_none(self):
        assert _extraer_json("{no es json") is None
        assert _extraer_json("") is None

    def test_acto_desconocido_cae_en_otro(self):
        assert _veredicto_desde_json({"acto": "fiesta", "hay_consulta": False}).acto == "otro"

    def test_bool_como_cadena(self):
        assert _veredicto_desde_json({"acto": "otro", "hay_consulta": "true"}).hay_consulta is True
        assert _veredicto_desde_json({"acto": "otro", "hay_consulta": "no"}).hay_consulta is False

    def test_confianza_se_acota_y_termino_se_limpia(self):
        v = _veredicto_desde_json(
            {"acto": "consulta_medicamento", "hay_consulta": True,
             "termino": "  atamel   forte. ", "confianza": 7}
        )
        assert v.confianza == 1.0
        assert v.termino == "atamel forte"

    def test_termino_se_ignora_si_no_hay_consulta(self):
        v = _veredicto_desde_json(
            {"acto": "dato_personal", "hay_consulta": False, "termino": "bolivar"}
        )
        assert v.termino is None

    def test_actos_declarados(self):
        assert "consulta_medicamento" in ACTOS and "atributo_producto" in ACTOS


# ------------------------------------------------------------------------ capa ---

class TestCapa:
    def test_capa_no_se_llama_cuando_el_camino_rapido_ya_decidio(self):
        llm = FakeLlm(_veredicto("otro", False))
        ent = asyncio.run(entender("vivacina", llm=llm, settings=Settings(),
                                   termino_candidato="vivacina"))
        assert ent.hay_consulta is True
        assert llm.llamadas == 0, "el camino rápido no debe gastar una llamada"

    def test_queja_del_laboratorio_no_es_consulta(self):
        """«No puede ser Indu.» — el cliente habla del laboratorio."""
        llm = FakeLlm(_veredicto("atributo_producto", False))
        ent = asyncio.run(entender("No puede ser Indu.", llm=llm, settings=Settings(),
                                   termino_candidato="ser indu"))
        assert ent.hay_consulta is False
        assert ent.acto == "atributo_producto"
        assert ent.termino is None
        assert llm.llamadas == 1

    @pytest.mark.parametrize("texto,candidato,acto", [
        ("Vivo en Ciudad Bolivar.", "vivo ciudad bolivar", "dato_personal"),
        ("Solo una marca?", "marca", "atributo_producto"),
        ("Por ahroa no", "ahroa", "dilatoria"),
        ("que Dios te bendiga", None, "cortesia"),
    ])
    def test_las_otras_quejas_tampoco_disparan_busqueda(self, texto, candidato, acto):
        llm = FakeLlm(_veredicto(acto, False))
        ent = asyncio.run(entender(texto, llm=llm, settings=Settings(),
                                  termino_candidato=candidato))
        assert ent.hay_consulta is False and ent.acto == acto

    def test_consulta_legitima_con_contexto_si_busca(self):
        """Frase larga sin verbo de consulta: no hay camino rápido, decide la capa."""
        llm = FakeLlm(_veredicto("consulta_medicamento", True, "diclofenaco 50", 0.85))
        ent = asyncio.run(entender("el diclofencao de 50 ese lo llevo yo",
                                  llm=llm, settings=Settings(),
                                  termino_candidato="diclofencao 50",
                                  producto_previo="MACRODANTINA 100 MG X 20 CAP"))
        assert ent.hay_consulta is True
        assert ent.termino == "diclofenaco 50"
        assert ent.fuente == "capa"
        assert llm.llamadas == 1

    def test_mensaje_con_verbo_lo_juzga_la_capa(self):
        """El verbo ya no decide: 'precio de X' va a la capa, que confirma el término."""
        llm = FakeLlm(_veredicto("consulta_medicamento", True, "macrodantina 100", 0.9))
        ent = asyncio.run(entender("precio de la macrodantina de 100",
                                  llm=llm, settings=Settings(),
                                  termino_candidato="macrodantina"))
        assert ent.hay_consulta is True and ent.fuente == "capa"
        assert ent.termino == "macrodantina 100"
        assert llm.llamadas == 1

    def test_la_capa_recibe_contexto_util(self):
        llm = FakeLlm(_veredicto("atributo_producto", False))
        asyncio.run(entender("Solo una marca?", llm=llm, settings=Settings(),
                             termino_candidato="marca", producto_previo="ATAMEL FORTE"))
        prompt = llm.ultimos_mensajes[-1]["content"]
        assert "Solo una marca?" in prompt
        assert "ATAMEL FORTE" in prompt          # producto mostrado antes
        assert "marca" in prompt                  # candidato sospechoso, para juzgarlo

    # ----------------------------------------------------------------- fail-safe ---

    def test_failsafe_si_el_proveedor_falla(self):
        llm = FakeLlm(error=RuntimeError("connection error"))
        ent = asyncio.run(entender("Solo una marca?", llm=llm, settings=Settings(),
                                  termino_candidato="marca"))
        assert ent.hay_consulta is None and ent.fuente == "fail-safe"

    def test_failsafe_si_el_json_es_invalido(self):
        llm = FakeLlm("perdón, no entendí la pregunta")
        ent = asyncio.run(entender("Solo una marca?", llm=llm, settings=Settings(),
                                  termino_candidato="marca"))
        assert ent.hay_consulta is None and ent.fuente == "fail-safe"

    def test_failsafe_por_timeout(self):
        llm = FakeLlm(_veredicto("otro", False), demora=0.5)
        ent = asyncio.run(entender("Solo una marca?", llm=llm, settings=Settings(intent_timeout=0.05),
                                  termino_candidato="marca"))
        assert ent.hay_consulta is None and ent.fuente == "fail-safe"
        assert "timeout" in ent.motivo

    def test_capa_apagada_no_es_concluyente(self):
        llm = FakeLlm(_veredicto("otro", False))
        ent = asyncio.run(entender("Solo una marca?", llm=llm, settings=Settings(intent_layer=False),
                                  termino_candidato="marca"))
        assert ent.hay_consulta is None and ent.fuente == "desactivada"
        assert llm.llamadas == 0

    def test_entendimiento_concluyente(self):
        assert Entendimiento(hay_consulta=False).concluyente
        assert Entendimiento(hay_consulta=True).concluyente
        assert not Entendimiento(hay_consulta=None).concluyente


# -------------------------------------------------------------------- auditoría ---

class TestAuditoria:
    def test_med_queries_guarda_el_veredicto(self):
        store = MemoryStore()
        asyncio.run(store.log_med_query(
            conversation_id=1, provider_id="demo", term="atamel 500",
            product_id="p1", product_name="ATAMEL 500", result_count=1,
            intent={"fuente": "capa", "acto": "consulta_medicamento",
                    "motivo": "pedido claro", "confianza": 0.91},
        ))
        fila = store.med_queries[-1]
        assert fila["intent"]["fuente"] == "capa"
        assert fila["intent"]["confianza"] == 0.91

    def test_med_queries_sin_capa_no_revienta(self):
        store = MemoryStore()
        asyncio.run(store.log_med_query(
            conversation_id=1, provider_id="demo", term="x", product_id=None,
            product_name=None, result_count=0,
        ))
        assert store.med_queries[-1]["intent"] == {}


# --------------------------------------------------------------- cableado (turn) ---

class TestCableadoTurno:
    def test_la_capa_es_el_decisor_y_el_heuritico_solo_failsafe(self):
        fuente = (RAIZ / "app" / "turn.py").read_text(encoding="utf-8")
        assert "entender_intencion(" in fuente
        # El heurístico de forma sobrevive SOLO en los caminos sin capa (apagada/fail-safe).
        assert fuente.count("_parece_consulta_medicamento(user_text)") <= 2
        assert "intent_layer" in fuente

    def test_migracion_de_auditoria_existe(self):
        sql = (RAIZ / "migrations" / "014_med_queries_intent.sql").read_text(encoding="utf-8")
        for columna in ("intent_fuente", "intent_acto", "intent_motivo", "intent_confianza"):
            assert columna in sql

    def test_la_capa_no_toca_los_guards(self):
        """La capa decide ANTES de buscar: `guards.py` no debe CONOCERLA.

        Nota: `guards.py` ya tenía un `intencion_fuera_kb` de antes de F15 (su propio
        filtro léxico); lo que no puede aparecer es un acoplamiento con la capa nueva.
        """
        guards = (RAIZ / "app" / "guards.py").read_text(encoding="utf-8")
        assert "app.intencion" not in guards
        assert "entender_intencion" not in guards
        assert "intent_layer" not in guards
