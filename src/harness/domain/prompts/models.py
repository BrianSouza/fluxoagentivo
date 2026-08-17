"""Prompt template contract.

Every prompt carries a semantic version and, when it produces structured
output, a JSON schema. Model calls record the version they used so a
knowledge record can always be traced back to how it was produced.
"""

import re
from dataclasses import dataclass, field
from string import Template
from typing import Any

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


class MissingPromptVariableError(KeyError):
    """Raised when rendering a template without all required variables."""


@dataclass(frozen=True, slots=True)
class PromptTemplate:
    name: str
    version: str
    template: str
    system: str | None = None
    json_schema: dict[str, Any] | None = None
    description: str = ""
    variables: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("prompt name must not be empty")
        if not _SEMVER.match(self.version):
            raise ValueError(
                f"prompt {self.name!r} needs a semantic version, got {self.version!r}"
            )
        if not self.template.strip():
            raise ValueError(f"prompt {self.name!r} has an empty template")

    @property
    def reference(self) -> str:
        """Identifier recorded on every model call using this prompt."""
        return f"{self.name}@{self.version}"

    def render(self, **values: Any) -> str:
        missing = [name for name in self.variables if name not in values]
        if missing:
            raise MissingPromptVariableError(
                f"prompt {self.reference} requires {sorted(missing)}"
            )
        try:
            return Template(self.template).substitute(**values)
        except KeyError as exc:  # a placeholder the manifest did not declare
            raise MissingPromptVariableError(
                f"prompt {self.reference} references undeclared variable {exc.args[0]!r}"
            ) from exc
