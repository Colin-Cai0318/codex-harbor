import pytest

from codex_harbor.codex import ModelRegistry, ModelValidationError
from codex_harbor.domain import ErrorType

MODELS = [
    {
        "model": "model-a",
        "displayName": "Model A",
        "isDefault": True,
        "defaultReasoningEffort": "medium",
        "supportedReasoningEfforts": [
            {"reasoningEffort": "low", "description": ""},
            {"reasoningEffort": "medium", "description": ""},
            {"reasoningEffort": "high", "description": ""},
        ],
    },
    {
        "model": "model-b",
        "displayName": "Model B",
        "isDefault": False,
        "defaultReasoningEffort": "low",
        "supportedReasoningEfforts": [{"reasoningEffort": "low", "description": ""}],
    },
]


def test_hidden_model_is_resolvable_for_recovery_but_marked_hidden():
    registry = ModelRegistry(
        MODELS
        + [
            {
                "model": "gpt-reserve",
                "displayName": "GPT-Reserve",
                "hidden": True,
                "defaultReasoningEffort": "xhigh",
                "supportedReasoningEfforts": [
                    {"reasoningEffort": "xhigh", "description": ""}
                ],
            }
        ]
    )
    assert registry.models["gpt-reserve"].hidden
    config = registry.resolve(
        task_model="gpt-reserve",
        task_reasoning="xhigh",
        global_model=None,
        global_reasoning="medium",
    )
    assert config.effective_model == "gpt-reserve"


def test_resolves_task_override_and_effective_config():
    config = ModelRegistry(MODELS).resolve(
        task_model="model-b",
        task_reasoning="low",
        global_model=None,
        global_reasoning="medium",
    )
    assert config.effective_model == "model-b"
    assert config.effective_reasoning_effort == "low"


def test_unknown_model_blocks_without_fallback():
    with pytest.raises(ModelValidationError) as raised:
        ModelRegistry(MODELS).resolve(
            task_model="unknown",
            task_reasoning="low",
            global_model=None,
            global_reasoning="medium",
        )
    assert raised.value.error_type == ErrorType.MODEL_UNAVAILABLE


def test_unsupported_reasoning_blocks_without_fallback():
    with pytest.raises(ModelValidationError) as raised:
        ModelRegistry(MODELS).resolve(
            task_model="model-b",
            task_reasoning="xhigh",
            global_model=None,
            global_reasoning="medium",
        )
    assert raised.value.error_type == ErrorType.REASONING_NOT_SUPPORTED
