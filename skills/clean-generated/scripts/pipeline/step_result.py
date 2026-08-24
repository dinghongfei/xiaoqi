"""Shared result type for pipeline steps."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class StepResult:
    status: str  # ok | error
    message: str

    @property
    def ok(self) -> bool:
        return self.status == "ok"
