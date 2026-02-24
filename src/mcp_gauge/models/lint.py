"""リンティング結果のデータモデル。"""

from enum import StrEnum

from pydantic import BaseModel


class Severity(StrEnum):
    """リンティング結果の重大度。"""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class LintResult(BaseModel):
    """リンティング結果。"""

    tool_name: str
    severity: Severity
    rule: str
    message: str
    suggestion: str
    field: str
