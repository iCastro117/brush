"""
Image / Figma -> design specification.

The audit engine measures against a normalised spec, not against a picture. That
boundary is deliberate: a screenshot has no tokens, no states, and no intent, so
anything read from pixels is an inference. This module makes that inference
explicit and reviewable instead of hiding it inside the audit.

Three inputs are supported:

  *.json        already a spec. Used directly, no model involved.
  *.png/.jpg    a mockup. Claude reads it and drafts a spec, which a human must
                confirm before it is used as a source of truth.
  figma://…     a Figma node. Converted by the REST adapter; needs FIGMA_TOKEN.

The drafted spec is written next to the image with a `.draft.json` suffix and
carries `"review_status": "unconfirmed"`. `load_design` refuses an unconfirmed
draft unless `--accept-drafted-spec` is passed, because a mis-read mockup would
turn every downstream measurement into a confident, well-evidenced fiction. That
is ground rule 05: a qualified human stays in the loop wherever the system's
output could be acted on.
"""
from __future__ import annotations

import base64
import json
import mimetypes
import os
from typing import Optional

SYSTEM = """You transcribe a UI mockup into a normalised design-system specification.

Report only what the image actually shows. Where a value is not legible, omit the property rather than estimating it — an omitted property is audited as "not specified", while a guessed one becomes a false finding that looks authoritative.

Infer the token layer where the image makes it obvious (a colour used by three components is a token), and name tokens by role, not by appearance: `brand-600`, not `blue`.

Reply with ONLY a JSON object in this shape, no prose and no code fences:
{"name": str, "root_font_size": 16, "grid_base": 4,
 "tokens": {"color": {...}, "space": {...}, "font_size": {...}, "font_weight": {...}, "radius": {...}},
 "components": [{"name": "Group/Variant", "role": "button|input|card|heading|body|label|listitem|alert|status",
                 "selector_hint": "", "text": "", "on_background": "{color.…}",
                 "props": {...}, "states": {...},
                 "confidence": 0.0-1.0, "unreadable": ["property names you could not determine"]}]}
"""

IMAGE_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp"}


def is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXT


def is_figma(ref: str) -> bool:
    return ref.startswith("figma://") or "figma.com/" in ref


def draft_spec_from_image(
    image_path: str,
    provider,
    out_path: Optional[str] = None,
    max_tokens: int = 4000,
) -> tuple[str, dict]:
    """
    Draft a specification from a mockup. Returns (path, spec).

    Requires a vision-capable provider (`anthropic`). The offline policy cannot
    read an image and says so rather than inventing a plausible spec.
    """
    if provider.name == "offline":
        raise RuntimeError(
            "Reading a mockup needs a vision model. Run with --provider anthropic "
            "(and ANTHROPIC_API_KEY set), or supply a design.spec.json directly."
        )

    with open(image_path, "rb") as fh:
        data = base64.standard_b64encode(fh.read()).decode()
    media_type = mimetypes.guess_type(image_path)[0] or "image/png"

    text = _vision_call(provider, SYSTEM, data, media_type, max_tokens)
    if text.strip().startswith("```"):
        text = text.split("\n", 1)[-1].rsplit("```", 1)[0]
    spec = json.loads(text)

    spec["review_status"] = "unconfirmed"
    spec["drafted_from"] = os.path.basename(image_path)
    spec["review_note"] = (
        "Drafted from a mockup by a vision model. Confirm every token and component "
        "value against the source before treating this as a specification. Change "
        "review_status to 'confirmed' once checked, or run with --accept-drafted-spec "
        "to audit against it as-is and have every finding marked provisional."
    )

    out_path = out_path or os.path.splitext(image_path)[0] + ".draft.json"
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, indent=2, ensure_ascii=False)
    return out_path, spec


def _vision_call(provider, system: str, b64: str, media_type: str, max_tokens: int) -> str:
    import anthropic

    client = anthropic.Anthropic()
    resp = client.messages.create(
        model=getattr(provider, "model", "claude-sonnet-4-6"),
        max_tokens=max_tokens,
        temperature=0.0,
        system=system,
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64",
                                         "media_type": media_type, "data": b64}},
            {"type": "text", "text": "Transcribe this mockup into a specification."},
        ]}],
    )
    return "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")


def spec_review_status(spec_path: str) -> str:
    """`confirmed` | `unconfirmed` | `native` (a spec that was never drafted)."""
    try:
        with open(spec_path, "r", encoding="utf-8") as fh:
            spec = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return "native"
    return spec.get("review_status", "native")


def resolve_design_ref(
    ref: str,
    provider=None,
    accept_drafted: bool = False,
    base_dir: str = "",
) -> tuple[str, str]:
    """
    Turn whatever the IMAGE/FIGMA column contains into a usable spec path.

    Returns (spec_path, note). Raises with an actionable message rather than
    guessing when the reference cannot be resolved.
    """
    ref = (ref or "").strip()
    if not ref:
        raise ValueError("no design reference given")
    path = ref if os.path.isabs(ref) else os.path.join(base_dir, ref)

    if is_figma(ref):
        raise NotImplementedError(
            "Figma references need the REST adapter and FIGMA_TOKEN. Export the node "
            "to design.spec.json first — see docs/ARCHITECTURE.md."
        )

    if is_image(path):
        draft = os.path.splitext(path)[0] + ".draft.json"
        if os.path.exists(draft) and spec_review_status(draft) == "confirmed":
            return draft, "spec drafted from the mockup and confirmed by a reviewer"
        if provider is None:
            raise RuntimeError(f"{os.path.basename(path)} is a mockup and no model was "
                               f"supplied to read it")
        draft, _ = draft_spec_from_image(path, provider, draft)
        if not accept_drafted:
            raise RuntimeError(
                f"drafted a specification at {os.path.basename(draft)}. Review it, set "
                f"review_status to 'confirmed', and re-run — or pass "
                f"--accept-drafted-spec to audit against the unconfirmed draft."
            )
        return draft, "PROVISIONAL — audited against an unconfirmed drafted spec"

    if not os.path.exists(path):
        raise FileNotFoundError(f"design reference not found: {ref}")
    status = spec_review_status(path)
    if status == "unconfirmed" and not accept_drafted:
        raise RuntimeError(
            f"{os.path.basename(path)} is an unconfirmed drafted spec. Confirm it or "
            f"pass --accept-drafted-spec."
        )
    note = {"confirmed": "spec drafted from a mockup and confirmed",
            "unconfirmed": "PROVISIONAL — unconfirmed drafted spec",
            "native": ""}[status]
    return path, note
