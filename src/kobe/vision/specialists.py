"""Per-app vision specialists.

The vision backend gets a single `question` string. That string is what the
multimodal model anchors on, so a thoughtful frame around the user's words
materially improves answers — especially for niche apps the model has weaker
priors about (Bambu Studio, FreeCAD).

This module owns one thing: turning `(user_question, WindowContext)` into the
final `question` payload. It's a pure function backed by a registry dict so
adding a new app means appending one entry, not editing logic.

The registry is keyed on `WindowContext.name` (lower-snake-case identifiers
like ``"vscode"`` or ``"bambu_studio"``). Each entry is a `_Spec` of
`(default_q, framing)`. The framing may contain ``{app_label}``, which is
substituted from `context.app_label` so the same template can serve both
``chrome`` and ``firefox`` (or ``slack`` and ``discord``) without duplicating
the wording.

The output format is fixed:

    {framing}\\n\\nUser question: {question_or_default}

Anything that wants the *raw* user question still has it on the
`VisionRequested` event — this string is purely the prompt the backend sees.
"""
from __future__ import annotations

from dataclasses import dataclass

from kobe.vision.context import WindowContext


@dataclass(frozen=True)
class _Spec:
    """One app's prompt material."""

    default_q: str
    framing: str


# Source of truth for per-app framing. Add an entry to support a new app.
# Keep `framing` short — the backend already has its own system prompt; this
# is just the contextual hint that says "you're looking at X, focus on Y."
_REGISTRY: dict[str, _Spec] = {
    "vscode": _Spec(
        default_q="Describe what's currently open in this VS Code window.",
        framing=(
            "VS Code editor. Identify the open file (if visible), any "
            "errors, lint warnings, red squiggles, or diff markers. If the "
            "user asked something specific, focus on that."
        ),
    ),
    "bambu_studio": _Spec(
        default_q="What's the state of this Bambu Studio project?",
        framing=(
            "Bambu Studio (3D slicer). Note the loaded model, plate state, "
            "slice settings, supports, and warnings. If the user asks about "
            "settings, point at the relevant panel."
        ),
    ),
    "freecad": _Spec(
        default_q="Describe what's on the FreeCAD canvas.",
        framing=(
            "FreeCAD (parametric CAD). Identify the active workbench, "
            "sketches, constraints, and any model-tree errors."
        ),
    ),
    "fusion360": _Spec(
        default_q="What's open in Fusion 360?",
        framing=(
            "Fusion 360. Identify the active workspace, timeline state, and "
            "any obvious problems."
        ),
    ),
    "blender": _Spec(
        default_q="What's on the Blender canvas?",
        framing=(
            "Blender. Identify the active editor (3D viewport, shader, "
            "geometry nodes), selected objects, and any warning indicators."
        ),
    ),
    "obsidian": _Spec(
        default_q="What note is open?",
        framing=(
            "Obsidian. Identify the open note title, headings, and the "
            "graph or links pane if visible."
        ),
    ),
    "chrome": _Spec(
        default_q="What page is open?",
        framing=(
            "{app_label} browser window. Identify the page title, URL if "
            "visible, and main content. Keep it tight."
        ),
    ),
    "firefox": _Spec(
        default_q="What page is open?",
        framing=(
            "{app_label} browser window. Identify the page title, URL if "
            "visible, and main content. Keep it tight."
        ),
    ),
    "excel": _Spec(
        default_q="What's in this spreadsheet?",
        framing=(
            "Excel spreadsheet. Identify the active sheet, visible columns, "
            "and any obvious formulas or chart."
        ),
    ),
    "slack": _Spec(
        default_q="What's the latest message?",
        framing=(
            "{app_label} chat. Identify the active channel and the most "
            "recent visible messages, without quoting personal content "
            "beyond what's necessary."
        ),
    ),
    "discord": _Spec(
        default_q="What's the latest message?",
        framing=(
            "{app_label} chat. Identify the active channel and the most "
            "recent visible messages, without quoting personal content "
            "beyond what's necessary."
        ),
    ),
    "terminal": _Spec(
        default_q="What's on the terminal?",
        framing=(
            "Terminal. Read the most recent command, its output, and call "
            "out any error messages or stack traces precisely."
        ),
    ),
    "explorer": _Spec(
        default_q="What folder is open?",
        framing=(
            "File Explorer. Identify the path and the visible file types "
            "and counts."
        ),
    ),
    "generic": _Spec(
        default_q="Describe what's on the screen.",
        framing="Unidentified application window. Be helpful and concise.",
    ),
}


def _spec_for(name: str) -> _Spec:
    """Lookup with a `generic` safety net so callers never need to branch."""
    return _REGISTRY.get(name, _REGISTRY["generic"])


def augment_question(question: str, context: WindowContext) -> str:
    """Wrap the user's raw question with app-specific framing.

    Returns a single string that the vision backend will use as `question`.
    If `question` is empty/whitespace, the per-app default is substituted in
    (so the model still gets a concrete instruction rather than `""`).
    """
    spec = _spec_for(context.name)

    # `app_label` is only meaningful when the framing template references it.
    # `str.format` raises KeyError on stray placeholders, so we only call it
    # for entries that opted in — keeps simple framings free of escaping.
    framing = spec.framing
    if "{app_label}" in framing:
        framing = framing.format(app_label=context.app_label)

    user_q = question.strip() or spec.default_q
    return f"{framing}\n\nUser question: {user_q}"
