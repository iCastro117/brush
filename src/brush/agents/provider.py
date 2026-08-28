"""
Model provider abstraction.

Three backends, and the difference between them is stated plainly everywhere it
matters, because a benchmark that hides which engine produced its numbers is not
a benchmark.

  anthropic  Real Claude via the Messages API. Needs ANTHROPIC_API_KEY.
             Non-deterministic; this is the mode the tool actually ships in.

  replay     Replays a cassette recorded from a previous `anthropic` run,
             keyed by a hash of the prompt. Byte-identical results on every
             machine, no key, no network. This is how a judge reproduces our
             live numbers exactly rather than approximately.

  offline    A deterministic scripted policy. It is NOT a language model and we
             never present it as one. It exists so the pipeline, the tool loop,
             the verifier and the trajectory writer can be exercised end to end
             with no credentials -- and so the architecture's contribution can
             be measured separately from the model's. Any figure produced in
             this mode is labelled `offline` in the results file.

Recording is on by default in `anthropic` mode, so a live run automatically
produces the cassette that makes it reproducible.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

DEFAULT_MODEL = "claude-sonnet-4-6"


@dataclass
class Completion:
    text: str
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    latency_ms: float = 0.0
    cached: bool = False

    @property
    def cost_usd(self) -> float:
        # Published Sonnet pricing: $3 / MTok in, $15 / MTok out.
        return (self.input_tokens * 3.0 + self.output_tokens * 15.0) / 1_000_000


def prompt_key(system: str, user: str, model: str) -> str:
    h = hashlib.sha256()
    h.update(model.encode())
    h.update(b"\x00")
    h.update(system.encode())
    h.update(b"\x00")
    h.update(user.encode())
    return h.hexdigest()[:24]


class Provider:
    name = "base"

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> Completion:
        raise NotImplementedError


class AnthropicProvider(Provider):
    name = "anthropic"

    def __init__(self, model: str = DEFAULT_MODEL, cassette_path: Optional[str] = None,
                 record: bool = True, temperature: float = 0.0):
        self.model = model
        self.temperature = temperature
        self.cassette_path = cassette_path
        self.record = record and cassette_path is not None
        self._cassette: dict[str, dict] = {}
        if cassette_path and os.path.exists(cassette_path):
            with open(cassette_path, "r", encoding="utf-8") as fh:
                self._cassette = json.load(fh)
        # Fail here, with an actionable message, rather than deep inside the
        # first completion call when a run is already half-finished.
        import importlib.util

        if importlib.util.find_spec("anthropic") is None:
            raise RuntimeError(
                "provider=anthropic needs the SDK. Install it with:\n"
                "  pip install anthropic          (or: pip install -e '.[live]')"
            )
        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError("provider=anthropic needs ANTHROPIC_API_KEY in the environment")

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> Completion:
        import anthropic

        client = anthropic.Anthropic()
        t0 = time.time()
        resp = client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=self.temperature,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        dt = (time.time() - t0) * 1000
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
        c = Completion(text, "anthropic", self.model,
                       resp.usage.input_tokens, resp.usage.output_tokens, dt)
        if self.record:
            key = prompt_key(system, user, self.model)
            self._cassette[key] = {
                "text": text, "model": self.model,
                "input_tokens": c.input_tokens, "output_tokens": c.output_tokens,
                "latency_ms": round(dt, 1),
            }
            with open(self.cassette_path, "w", encoding="utf-8") as fh:
                json.dump(self._cassette, fh, indent=2)
        return c


class ReplayProvider(Provider):
    name = "replay"

    def __init__(self, cassette_path: str, model: str = DEFAULT_MODEL,
                 on_miss: Optional[Callable[[str, str], str]] = None):
        self.model = model
        self.cassette_path = cassette_path
        self.on_miss = on_miss
        if not os.path.exists(cassette_path):
            raise FileNotFoundError(
                f"no cassette at {cassette_path}. Record one first with "
                f"--provider anthropic --cassette {cassette_path}"
            )
        with open(cassette_path, "r", encoding="utf-8") as fh:
            self._cassette = json.load(fh)
        self.misses = 0

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> Completion:
        key = prompt_key(system, user, self.model)
        entry = self._cassette.get(key)
        if entry is None:
            self.misses += 1
            if self.on_miss is None:
                raise KeyError(
                    f"cassette miss ({key}). The prompt changed since recording; "
                    f"re-record with --provider anthropic."
                )
            return Completion(self.on_miss(system, user), "replay-miss", self.model)
        return Completion(entry["text"], "replay", entry.get("model", self.model),
                          entry.get("input_tokens", 0), entry.get("output_tokens", 0),
                          entry.get("latency_ms", 0.0), cached=True)


class OfflineProvider(Provider):
    """
    Deterministic scripted policy. Not a language model.

    Handlers are registered by task name. Each receives the parsed task payload
    and returns the JSON string an LLM would have returned, so every downstream
    component -- parser, verifier, retry loop, trajectory -- runs unchanged.
    """

    name = "offline"

    def __init__(self, model: str = "offline-policy-v1"):
        self.model = model
        self._handlers: dict[str, Callable[[dict], Any]] = {}

    def register(self, task: str, fn: Callable[[dict], Any]) -> None:
        self._handlers[task] = fn

    def complete(self, system: str, user: str, max_tokens: int = 1500) -> Completion:
        t0 = time.time()
        try:
            payload = json.loads(user)
        except json.JSONDecodeError:
            payload = {"task": "unknown", "raw": user}
        task = payload.get("task", "unknown")
        fn = self._handlers.get(task)
        if fn is None:
            out: Any = {"error": f"no offline handler for task '{task}'"}
        else:
            out = fn(payload)
        text = json.dumps(out)
        # Token counts are the real character counts / 4, so cost comparisons
        # between modes stay on the same footing rather than reading as zero.
        return Completion(text, "offline", self.model,
                          input_tokens=len(system + user) // 4,
                          output_tokens=len(text) // 4,
                          latency_ms=(time.time() - t0) * 1000)


def build_provider(kind: str, cassette: Optional[str] = None,
                   model: str = DEFAULT_MODEL) -> Provider:
    kind = (kind or "offline").lower()
    if kind == "anthropic":
        return AnthropicProvider(model=model, cassette_path=cassette)
    if kind == "replay":
        if not cassette:
            raise ValueError("provider=replay requires --cassette")
        return ReplayProvider(cassette, model=model)
    if kind == "offline":
        return OfflineProvider()
    raise ValueError(f"unknown provider '{kind}' (anthropic | replay | offline)")
