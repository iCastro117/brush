"""
The approved-deviation ledger: the agent's memory across runs.

A design-system audit that reports the same twelve intentional deviations on
every commit gets muted within a week, and once it is muted the real regressions
sail through with it. The failure mode is not a bad finding -- it is a correct
finding repeated until nobody reads the report.

So the tool remembers. When a reviewer marks a deviation intentional, the
decision is recorded with who approved it, why, and what the measured values
were at approval time. Later runs suppress it -- but only while the measurement
still matches. If the value drifts further, the approval no longer covers it and
the finding comes back. An approval is scoped to a number, not to a property
name, which is what stops the ledger becoming a permanent blindfold.

Approvals are also the human checkpoint required by ground rules 04 and 05: no
finding is ever silently dismissed by the agent on its own authority.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Any, Optional


@dataclass
class Approval:
    approval_id: str
    node_key: str
    prop: str
    approved_code_value: Any
    tolerance: float
    reason: str
    approved_by: str
    approved_at: float
    expires_after_days: Optional[int] = None

    def covers(self, code_value: Any) -> bool:
        """An approval is scoped to the value it was granted for."""
        try:
            a, b = float(self.approved_code_value), float(code_value)
            return abs(a - b) <= self.tolerance
        except (TypeError, ValueError):
            return str(self.approved_code_value).strip().lower() == str(code_value).strip().lower()

    def expired(self, now: Optional[float] = None) -> bool:
        if not self.expires_after_days:
            return False
        now = now or time.time()
        return (now - self.approved_at) > self.expires_after_days * 86400


class Ledger:
    def __init__(self, path: Optional[str] = None):
        self.path = path
        self.approvals: list[Approval] = []
        if path and os.path.exists(path):
            self.load(path)

    def load(self, path: str) -> None:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"the ledger at {path} is not valid JSON (line {exc.lineno}): {exc.msg}"
            ) from exc
        try:
            self.approvals = [Approval(**a) for a in data.get("approvals", [])]
        except TypeError as exc:
            raise ValueError(
                f"the ledger at {path} has entries this version does not understand: {exc}"
            ) from exc

    def save(self, path: Optional[str] = None) -> None:
        path = path or self.path
        if not path:
            return
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "approvals": [asdict(a) for a in self.approvals]},
                      fh, indent=2)

    def approve(self, node_key: str, prop: str, code_value: Any, reason: str,
                approved_by: str, tolerance: float = 0.5,
                expires_after_days: Optional[int] = 180) -> Approval:
        a = Approval(
            approval_id=f"APR-{len(self.approvals) + 1:03d}",
            node_key=node_key, prop=prop, approved_code_value=code_value,
            tolerance=tolerance, reason=reason, approved_by=approved_by,
            approved_at=time.time(), expires_after_days=expires_after_days,
        )
        self.approvals.append(a)
        return a

    def lookup(self, node_key: str, prop: str) -> Optional[dict]:
        for a in self.approvals:
            if a.node_key == node_key and a.prop == prop and not a.expired():
                return asdict(a)
        return None

    def suppresses(self, node_key: str, prop: str, code_value: Any) -> Optional[Approval]:
        """Only suppress while the measured value still falls inside the approval."""
        for a in self.approvals:
            if a.node_key != node_key or a.prop != prop or a.expired():
                continue
            if a.covers(code_value):
                return a
        return None

    def stats(self) -> dict:
        return {"approvals": len(self.approvals),
                "expired": sum(1 for a in self.approvals if a.expired())}
