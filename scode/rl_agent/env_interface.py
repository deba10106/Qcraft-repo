from abc import ABC, abstractmethod
from typing import Any, Tuple
from gymnasium import spaces

class RLMappingEnvInterface(ABC):
    """
    Minimal interface all mapping RL environments must satisfy.
    Keeps Stable-Baselines3 compatibility while enabling family-specific logic.
    """
    @property
    @abstractmethod
    def action_space(self) -> spaces.Space:
        ...

    @property
    @abstractmethod
    def observation_space(self) -> spaces.Space:
        ...

    @abstractmethod
    def reset(self, seed: int | None = None, options: dict | None = None) -> Tuple[Any, dict]:
        ...

    @abstractmethod
    def step(self, action: Any) -> Tuple[Any, float, bool, bool, dict]:
        ...

    # Optional utility for logging/analysis hooks
    def get_mapping_info(self) -> dict:
        return {}
