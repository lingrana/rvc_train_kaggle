"""
Module defining models for representing configuration settings for
UI tabs (Training Only).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from functools import cached_property

from pydantic import BaseModel

from ultimate_rvc.web.config.component import AnyComponentConfig, ComponentConfig
from ultimate_rvc.web.config.tab import TrainingConfig

if TYPE_CHECKING:
    import gradio as gr


class MultiStepTrainingConfig(TrainingConfig):
    """Configuration settings for multi-step training tab."""


class TotalTrainingConfig(BaseModel):
    """
    All configuration settings for training tabs.

    Attributes
    ----------
    multi_step : MultiStepTrainingConfig
        Configuration settings for the multi-step training tab.

    """

    multi_step: MultiStepTrainingConfig = MultiStepTrainingConfig()


class TotalConfig(BaseModel):
    """
    All configuration settings for the Ultimate RVC app (Training Only).

    Attributes
    ----------
    training : TotalTrainingConfig
        Configuration settings for training tabs.

    """

    training: TotalTrainingConfig = TotalTrainingConfig()

    @cached_property
    def all(self) -> list[AnyComponentConfig]:
        """
        Recursively collect those component configuration models nested
        within the current model instance, which have values that are
        not excluded.

        Returns
        -------
        list[AnyComponentConfig]
            A list of component configuration models found within the
            current model instance, which have values that are not
            excluded.

        """

        def _collect(model: BaseModel) -> list[AnyComponentConfig]:
            component_configs: list[Any] = []
            for _, value in model:
                if isinstance(value, ComponentConfig):
                    if not value.exclude_value:
                        component_configs.append(value)
                elif isinstance(value, BaseModel):
                    component_configs.extend(_collect(value))
            return component_configs

        return _collect(self)
