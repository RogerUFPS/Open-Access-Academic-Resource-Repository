import unittest
from biblioteca_agent.dialogue import resolve_turn, render_state
from biblioteca_agent.runtime import Intent, FilterClaim, AgentRuntime


class DialogueTests(unittest.TestCase):
    definitions = [
        {'id': 1, 'nombre': 'Idioma', 'clave': 'idioma', 'tipo': 'lista', 'valores_validos': ['es', 'en']},
        {'id': 2, 'nombre': 'Fecha de publicación', 'clave': 'fecha_publicacion', 'tipo': 'rango_anios'},
    ]

    def test_removal_variants_preserve_topic(self):
        for text in ['Ahora sin restricción de idioma, conserva el mismo tema', 'quita el idioma', 'remove language']:
            intent = Intent(tipo='buscar_literatura', tema='tema inventado', idioma='es', es_seguimiento=True)
            claims, follow, removed = resolve_turn(text, 'tema original', intent, [], [FilterClaim(id=1, valor=['es'], evidencia='español')], self.definitions)
            self.assertTrue(follow)
            self.assertEqual(removed, {1})
            self.assertEqual(claims, [])
            self.assertEqual(intent.tema, 'tema original')

    def test_new_topic_does_not_inherit_filters(self):
        intent = Intent(tipo='buscar_literatura', tema='otro tema', idioma='es', es_seguimiento=True)
        claims, follow, _ = resolve_turn('Ahora busco investigaciones sobre otro tema', 'tema anterior', intent, [], [FilterClaim(id=1, valor=['en'], evidencia='inglés')], self.definitions)
        self.assertFalse(follow)
        self.assertEqual(claims, [])

    def test_explicit_new_operation_overrides_followup_flag(self):
        intent = Intent(tipo='buscar_literatura', tema='tema distinto', idioma='es', es_seguimiento=True, operacion='nueva')
        _, follow, _ = resolve_turn('Ahora un tema distinto', 'tema anterior', intent, [], [], self.definitions)
        self.assertFalse(follow)

    def test_canonical_state_keeps_language_parseable(self):
        claims = [FilterClaim(id=1, valor=['en'], evidencia='inglés')]
        state = render_state('tema', [], claims)
        self.assertEqual(AgentRuntime.extract_filters(state, self.definitions)[0].valor, ['en'])

    def test_removing_period_does_not_remove_language(self):
        intent = Intent(tipo='buscar_literatura', tema='tema', idioma='es', operacion='filtros')
        old = [FilterClaim(id=1, valor=['es'], evidencia='español'), FilterClaim(id=2, valor='>=2023', evidencia='desde 2023')]
        claims, _, removed = resolve_turn('sin restricción de fecha', 'tema', intent, [], old, self.definitions)
        self.assertEqual(removed, {2})
        self.assertEqual([c.id for c in claims], [1])
