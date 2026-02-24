"""シナリオ定義のデータモデル。"""

from typing import Any

from pydantic import BaseModel


class SuccessCriteria(BaseModel):
    """シナリオの成功条件。"""

    max_steps: int | None = None
    required_tools: list[str] | None = None
    forbidden_tools: list[str] | None = None
    must_succeed: bool = True
    custom_assertions: list[str] | None = None


class ScenarioDefinition(BaseModel):
    """テストシナリオの定義。"""

    id: str
    name: str
    description: str
    task_instruction: str
    success_criteria: SuccessCriteria
    setup: list[dict[str, Any]] | None = None
    teardown: list[str] | None = None
