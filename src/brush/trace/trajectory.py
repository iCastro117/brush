"""
Trajectory recording.

A trajectory here is not a debug log. It is the artefact a reviewer reads to
decide whether they trust a finding, so it records the four things that make an
agent step auditable: what the agent was told, what it asked for, what the tool
actually returned, and what the agent did with the answer -- including the times
it was told it was wrong and had to try again.

Written as JSONL so a long run streams to disk instead of accumulating in RAM,
and so a single step can be grepped out of a 5,000-step run.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Optional


@dataclass
class Step:
    step_id: str
    agent: str
    kind: str            # instruction | thought | tool_call | tool_result | decision | retry | checkpoint | error
    summary: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)
    parent: Optional[str] = None
    duration_ms: Optional[float] = None


class Trajectory:
    def __init__(self, run_id: str, path: str, meta: Optional[dict] = None):
        self.run_id = run_id
        self.path = path
        self.steps: list[Step] = []
        self._fh = None
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._fh = open(path, "w", encoding="utf-8")
        self._write({"type": "run_meta", "run_id": run_id,
                     "started_at": time.time(), **(meta or {})})

    def _write(self, obj: dict) -> None:
        if self._fh:
            self._fh.write(json.dumps(obj, default=str) + "\n")
            self._fh.flush()

    def record(self, agent: str, kind: str, summary: str,
               payload: Optional[dict] = None, parent: Optional[str] = None,
               duration_ms: Optional[float] = None) -> str:
        step = Step(str(uuid.uuid4())[:8], agent, kind, summary,
                    payload or {}, parent=parent, duration_ms=duration_ms)
        self.steps.append(step)
        self._write({"type": "step", **asdict(step)})
        return step.step_id

    def close(self, stats: Optional[dict] = None) -> None:
        self._write({"type": "run_end", "run_id": self.run_id,
                     "ended_at": time.time(), "steps": len(self.steps),
                     "stats": stats or {}})
        if self._fh:
            self._fh.close()
            self._fh = None

    # -- reporting -------------------------------------------------------
    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for s in self.steps:
            out[s.kind] = out.get(s.kind, 0) + 1
        return out

    def to_markdown(self, title: str = "Agent trajectory") -> str:
        """Render the run as something a human will actually read."""
        icons = {"instruction": "▸", "thought": "·", "tool_call": "→",
                 "tool_result": "←", "decision": "✓", "retry": "↻",
                 "checkpoint": "⏸", "error": "✗"}
        lines = [f"# {title}", "", f"Run `{self.run_id}` — {len(self.steps)} steps", ""]
        counts = self.counts()
        lines.append("| step kind | count |")
        lines.append("|---|---|")
        for k, v in sorted(counts.items()):
            lines.append(f"| {k} | {v} |")
        lines.append("")

        current = None
        for s in self.steps:
            if s.agent != current:
                current = s.agent
                lines.append(f"\n## {s.agent}\n")
            icon = icons.get(s.kind, "•")
            lines.append(f"{icon} **{s.kind}** — {s.summary}")
            if s.payload:
                body = json.dumps(s.payload, indent=2, default=str)
                if len(body) > 1400:
                    body = body[:1400] + "\n  … truncated …"
                lines.append("")
                lines.append("```json")
                lines.append(body)
                lines.append("```")
            lines.append("")
        return "\n".join(lines)


def load_trajectory(path: str) -> list[dict]:
    out = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(json.loads(line))
    return out
