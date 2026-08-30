from pathlib import Path

import pytest

pytestmark = pytest.mark.provider_eval

from deepeval import assert_test
from deepeval.dataset import EvaluationDataset, Golden
from deepeval.test_case import LLMTestCase

from agent_arena.eval_target import run_ai_app
from metrics import SINGLE_TURN_NO_TRACING_METRICS

dataset = EvaluationDataset()
dataset.add_goldens_from_json_file(
    file_path=str(Path(__file__).with_name(".dataset.json"))
)


@pytest.mark.parametrize("golden", dataset.goldens)
def test_agent_arena_single_turn(golden: Golden):
    actual_output = run_ai_app(golden.input)
    test_case = LLMTestCase(
        input=golden.input,
        actual_output=actual_output,
        expected_output=getattr(golden, "expected_output", None),
        context=getattr(golden, "context", None),
        retrieval_context=getattr(golden, "retrieval_context", None),
    )
    assert_test(
        test_case=test_case,
        metrics=SINGLE_TURN_NO_TRACING_METRICS,
    )
