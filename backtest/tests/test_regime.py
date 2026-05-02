"""Tests del detector de régimen con histéresis direccional."""
import pandas as pd
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.macro.regime import detect_regime, make_regime_state, update_regime_state

FRI = pd.Timestamp


def _run_scores(scores: list[float]) -> list[str]:
    """Aplica una lista de scores secuencialmente, devuelve lista de regímenes."""
    state = make_regime_state()
    regimes = []
    for i, score in enumerate(scores):
        dt = FRI('2020-01-03') + pd.Timedelta(weeks=i)
        state = update_regime_state(score, state, dt)
        regimes.append(state['current_regime'])
    return regimes


class TestDetectRegime:
    def test_all_regimes(self):
        assert detect_regime(90) == 'Bull Pleno'
        assert detect_regime(80) == 'Bull Pleno'
        assert detect_regime(79) == 'Bull Maduro'
        assert detect_regime(60) == 'Bull Maduro'
        assert detect_regime(59) == 'Transición'
        assert detect_regime(40) == 'Transición'
        assert detect_regime(39) == 'Risk-OFF'
        assert detect_regime(20) == 'Risk-OFF'
        assert detect_regime(19) == 'Capitulación'
        assert detect_regime(0)  == 'Capitulación'

    def test_fallback_below_zero(self):
        assert detect_regime(-1) == 'Capitulación'


class TestRegimeHysteresis:

    def test_initialization_first_score(self):
        """Primer score válido establece régimen inmediatamente."""
        state = make_regime_state()
        state = update_regime_state(55, state, FRI('2020-01-03'))
        assert state['current_regime'] == 'Transición'
        assert state['pending_regime'] is None
        assert state['pending_streak'] == 0

    def test_no_change_inside_same_regime(self):
        """Score dentro del mismo régimen no genera pending."""
        regimes = _run_scores([55, 50, 45])
        assert all(r == 'Transición' for r in regimes)

    # Escenario 1: Subida justa — NO cambia
    def test_ascending_single_week_no_change(self):
        """
        Transición (55) → 64 durante 1 semana → 58 → NO cambia a Bull Maduro.
        diff = 64 − 60 = 4 < 5 → no supera umbral.
        """
        regimes = _run_scores([55, 64, 58])
        assert regimes[0] == 'Transición'
        assert regimes[1] == 'Transición'   # diff=4 < 5, no hay pending
        assert regimes[2] == 'Transición'

    # Escenario 2: Subida válida — SÍ cambia
    def test_ascending_two_weeks_changes(self):
        """
        Transición (55) → 65 dos semanas consecutivas → SÍ cambia a Bull Maduro.
        diff = 65 − 60 = 5 ≥ 5 → OK; persiste 2 semanas → confirma.
        """
        regimes = _run_scores([55, 65, 65])
        assert regimes[0] == 'Transición'
        assert regimes[1] == 'Transición'   # streak=1, no confirmado aún
        assert regimes[2] == 'Bull Maduro'  # streak=2, confirmado

    # Escenario 3: Subida insuficiente — NO cambia
    def test_ascending_insufficient_diff(self):
        """
        Transición (55) → 62 durante 4 semanas → NO cambia.
        diff = 62 − 60 = 2 < 5 → nunca supera umbral.
        """
        regimes = _run_scores([55, 62, 62, 62, 62])
        assert all(r == 'Transición' for r in regimes)

    # Escenario 4: Bajada válida — SÍ cambia
    def test_descending_two_weeks_changes(self):
        """
        Bull Maduro (70) → 54 dos semanas consecutivas → SÍ cambia a Transición.
        diff = 60 − 54 = 6 ≥ 5 → OK; persiste 2 semanas → confirma.
        """
        regimes = _run_scores([70, 54, 54])
        assert regimes[0] == 'Bull Maduro'
        assert regimes[1] == 'Bull Maduro'  # streak=1
        assert regimes[2] == 'Transición'   # confirmado

    def test_pending_resets_if_score_returns(self):
        """Si el score vuelve al régimen actual, el pending se resetea."""
        state = make_regime_state()
        dt = FRI('2020-01-03')
        state = update_regime_state(55, state, dt)           # Transición
        state = update_regime_state(65, state, dt + pd.Timedelta(weeks=1))  # pending=1
        assert state['pending_regime'] == 'Bull Maduro'
        assert state['pending_streak'] == 1
        state = update_regime_state(55, state, dt + pd.Timedelta(weeks=2))  # vuelve
        assert state['pending_regime'] is None
        assert state['pending_streak'] == 0
        assert state['current_regime'] == 'Transición'

    def test_none_score_preserves_state(self):
        """Score None no modifica el estado."""
        state = make_regime_state()
        dt = FRI('2020-01-03')
        state = update_regime_state(55, state, dt)
        original = dict(state)
        state = update_regime_state(None, state, dt + pd.Timedelta(weeks=1))
        assert state['current_regime'] == original['current_regime']
        assert state['pending_regime'] == original['pending_regime']

    def test_confirmed_after_exactly_2_streaks(self):
        """Confirmación ocurre en la semana 2 (no en la 3)."""
        regimes = _run_scores([55, 65, 65, 65])
        assert regimes[1] == 'Transición'   # semana 1 del cruce: no confirmado
        assert regimes[2] == 'Bull Maduro'  # semana 2: confirmado
        assert regimes[3] == 'Bull Maduro'  # semana 3: mantiene
