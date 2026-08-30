from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..domain import EffectiveAgentConfig, ErrorType
from .app_server_client import AppServerClient


class ModelValidationError(ValueError):
    def __init__(self, message: str, error_type: ErrorType):
        super().__init__(message)
        self.error_type = error_type


@dataclass(slots=True)
class ModelCapability:
    model: str
    display_name: str
    is_default: bool
    reasoning_efforts: set[str]
    default_reasoning_effort: str


class ModelRegistry:
    def __init__(self, models: list[dict[str, Any]]):
        self.models = {
            item["model"]: ModelCapability(
                model=item["model"],
                display_name=item.get("displayName", item["model"]),
                is_default=bool(item.get("isDefault")),
                reasoning_efforts={
                    option["reasoningEffort"]
                    for option in item.get("supportedReasoningEfforts", [])
                },
                default_reasoning_effort=item.get("defaultReasoningEffort", "medium"),
            )
            for item in models
        }

    @classmethod
    async def load(cls, client: AppServerClient) -> ModelRegistry:
        return cls(await client.model_list())

    def default_model(self) -> ModelCapability | None:
        return next((model for model in self.models.values() if model.is_default), None)

    def resolve(
        self,
        *,
        task_model: str | None,
        task_reasoning: str | None,
        global_model: str | None,
        global_reasoning: str = "medium",
        profile: dict[str, Any] | None = None,
    ) -> EffectiveAgentConfig:
        profile = profile or {}
        requested_model = (
            task_model if task_model is not None else profile.get("model", global_model)
        )
        requested_reasoning = (
            task_reasoning
            if task_reasoning is not None
            else profile.get("reasoning_effort", global_reasoning)
        )
        capability = (
            self.models.get(requested_model)
            if requested_model
            else self.default_model()
        )
        if requested_model and capability is None:
            raise ModelValidationError(
                f"model is unavailable: {requested_model}", ErrorType.MODEL_UNAVAILABLE
            )
        if capability is None:
            raise ModelValidationError(
                "Codex returned no default model", ErrorType.MODEL_UNAVAILABLE
            )
        effort = requested_reasoning or capability.default_reasoning_effort
        if effort == "default":
            effort = capability.default_reasoning_effort
        if effort not in capability.reasoning_efforts:
            raise ModelValidationError(
                f"model {capability.model} does not support reasoning effort {effort}",
                ErrorType.REASONING_NOT_SUPPORTED,
            )
        return EffectiveAgentConfig(
            requested_model=task_model,
            requested_reasoning_effort=task_reasoning,
            effective_model=capability.model,
            effective_reasoning_effort=effort,
        )
