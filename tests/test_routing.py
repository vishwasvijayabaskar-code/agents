"""Tests for orchestrator routing logic — no LLM calls needed."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from nodes.orchestrator import (
    _fast_route,
    _maybe_synthesize,
    _should_escalate_to_claude,
    _worker_nodes,
    route_decision,
)
from tests.conftest import make_state

# ---------------------------------------------------------------------------
# _fast_route
# ---------------------------------------------------------------------------

class TestFastRoute:
    def test_trivial_question_returns_fast(self):
        assert _fast_route("what is 2+2") == "FAST"

    def test_research_keyword_routes_researcher(self):
        assert _fast_route("research quantum computing") == "RESEARCHER"

    def test_explain_routes_researcher(self):
        assert _fast_route("explain how DNS works") == "RESEARCHER"

    def test_code_keyword_routes_coder(self):
        assert _fast_route("write a hello world in python") == "CODER"

    def test_build_keyword_routes_coder(self):
        assert _fast_route("build a login form") == "CODER"

    def test_long_task_returns_none(self):
        # >150 chars → must go through LLM
        long = "a" * 151
        assert _fast_route(long) is None

    def test_multi_hop_keyword_returns_none(self):
        assert _fast_route("research python then build an app") is None

    def test_after_that_returns_none(self):
        assert _fast_route("find the best library, after that write code") is None

    def test_step1_returns_none(self):
        assert _fast_route("step 1 research, step 2 implement") is None

    def test_find_and_returns_none(self):
        assert _fast_route("find and implement a sorting algorithm") is None

    def test_empty_short_is_fast(self):
        assert _fast_route("hello") == "FAST"


# ---------------------------------------------------------------------------
# _should_escalate_to_claude
# ---------------------------------------------------------------------------

class TestEscalation:
    def test_simple_coder_task_no_escalate(self):
        assert _should_escalate_to_claude("write a hello world", "CODER") is False

    def test_non_coder_route_no_escalate(self):
        assert _should_escalate_to_claude("build a scalable system", "RESEARCHER") is False

    def test_complex_keyword_escalates(self):
        assert _should_escalate_to_claude("build a production-grade auth system", "CODER") is True

    def test_scalable_escalates(self):
        assert _should_escalate_to_claude("implement scalable microservices", "CODER") is True

    def test_long_heavy_task_escalates(self):
        task = "write " + "a" * 200
        assert _should_escalate_to_claude(task, "CODER") is True

    def test_architect_escalates(self):
        assert _should_escalate_to_claude("architect a distributed system", "CODER") is True

    def test_short_no_complexity_no_escalate(self):
        assert _should_escalate_to_claude("write a sort function", "CODER") is False


# ---------------------------------------------------------------------------
# route_decision
# ---------------------------------------------------------------------------

class TestRouteDecision:
    def test_routes_to_coder(self):
        state = make_state(route="CODER", iterations=1)
        assert route_decision(state) == "CODER"

    def test_routes_to_researcher(self):
        state = make_state(route="RESEARCHER", iterations=1)
        assert route_decision(state) == "RESEARCHER"

    def test_routes_to_fast(self):
        state = make_state(route="FAST", iterations=1)
        assert route_decision(state) == "FAST"

    def test_done_flag_ends(self):
        state = make_state(route="CODER", done=True, iterations=1)
        assert route_decision(state) == "__end__"

    def test_iteration_cap_ends(self):
        state = make_state(route="CODER", iterations=3)
        assert route_decision(state) == "__end__"

    def test_no_rerun_agent(self):
        state = make_state(route="CODER", iterations=1, agent_outputs={"CODER": "done"})
        assert route_decision(state) == "__end__"

    def test_unknown_route_ends(self):
        state = make_state(route="UNKNOWNAGENT", iterations=1)
        assert route_decision(state) == "__end__"

    def test_null_route_ends(self):
        state = make_state(route=None, done=True)
        assert route_decision(state) == "__end__"

    def test_codex_demoted_to_coder_without_signal(self):
        state = make_state(route="CODEX", task="fix this bug", iterations=1)
        result = route_decision(state)
        assert result == "CODER"

    def test_codex_fires_with_signal(self):
        state = make_state(route="CODEX", task="build entire app from scratch", iterations=1)
        assert route_decision(state) == "CODEX"

    def test_codex_demoted_coder_already_ran_ends(self):
        state = make_state(
            route="CODEX",
            task="fix a bug",
            iterations=1,
            agent_outputs={"CODER": "done"},
        )
        assert route_decision(state) == "__end__"

    def test_synthesize_triggered_after_two_workers(self):
        state = make_state(
            route=None,
            done=True,
            iterations=2,
            agent_outputs={"CODER": "code result", "RESEARCHER": "research result"},
        )
        assert route_decision(state) == "SYNTHESIZE"

    def test_synthesize_not_triggered_for_single_worker(self):
        state = make_state(
            route=None,
            done=True,
            iterations=1,
            agent_outputs={"CODER": "code result"},
        )
        assert route_decision(state) == "__end__"

    def test_synthesize_not_triggered_if_already_ran(self):
        state = make_state(
            route=None,
            done=True,
            iterations=2,
            agent_outputs={
                "CODER": "code",
                "RESEARCHER": "research",
                "SYNTHESIZE": "merged",
            },
        )
        assert route_decision(state) == "__end__"


# ---------------------------------------------------------------------------
# _maybe_synthesize
# ---------------------------------------------------------------------------

class TestMaybeSynthesize:
    def test_no_workers_ends(self):
        assert _maybe_synthesize({}, _worker_nodes()) == "__end__"

    def test_one_worker_ends(self):
        assert _maybe_synthesize({"FAST": "hi"}, _worker_nodes()) == "__end__"

    def test_two_workers_synthesize(self):
        assert _maybe_synthesize({"FAST": "a", "CODER": "b"}, _worker_nodes()) == "SYNTHESIZE"

    def test_already_synthesized_ends(self):
        assert _maybe_synthesize({"FAST": "a", "CODER": "b", "SYNTHESIZE": "c"}, _worker_nodes()) == "__end__"
