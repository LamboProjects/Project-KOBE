"""Window-context detection for per-app vision routing.

Phase 4 ships a foreground-window screenshot to the vision pipeline. Different
apps need different framing — a CAD viewport question is nothing like a code
diff question — so we tag each capture with a coarse `WindowContext` derived
purely from the OS-reported window title.

The classifier is intentionally a small ordered list of substring rules rather
than a regex zoo: titles are noisy, vendors rebrand, and we want the failure
mode to be "fall through to generic" rather than "crash on a new app". Order
matters because some tokens overlap (e.g. "Studio" appears in both
"Visual Studio Code" and "Bambu Studio") — the more-specific needle wins by
appearing earlier in the rule list.

Example:
    >>> detect_context("foo.py - KOBE - Visual Studio Code").name
    'vscode'
    >>> detect_context("Random App 1.2").name
    'generic'

Pure function, no I/O. A future enhancement could add a `psutil`-based
process-name fallback for ambiguous titles (e.g. an untitled Electron window),
but that belongs in the capture layer, not here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class WindowContext:
    name: str
    """Canonical id used by routing. One of: vscode, bambu_studio, freecad,
    chrome, firefox, terminal, excel, slack, discord, fusion360, blender,
    obsidian, explorer, generic."""

    app_label: str
    """Human-readable app name for logs and prompts."""

    hints: tuple[str, ...]
    """Short tags useful for prompt routing and structured logging."""


# --- Context factories -------------------------------------------------------
# Tiny no-arg constructors keep the rule table compact and lazy-friendly.

def _vscode() -> WindowContext:
    return WindowContext("vscode", "VS Code", ("code", "errors", "editor", "diff"))

def _bambu() -> WindowContext:
    return WindowContext("bambu_studio", "Bambu Studio",
                         ("3d-print", "slicer", "print-settings", "gcode"))

def _freecad() -> WindowContext:
    return WindowContext("freecad", "FreeCAD", ("cad", "3d", "sketch", "constraint"))

def _fusion360() -> WindowContext:
    return WindowContext("fusion360", "Fusion 360", ("cad", "3d", "timeline", "sketch"))

def _blender() -> WindowContext:
    return WindowContext("blender", "Blender", ("3d", "mesh", "modeling", "render"))

def _obsidian() -> WindowContext:
    return WindowContext("obsidian", "Obsidian", ("notes", "markdown", "graph", "links"))

def _chrome() -> WindowContext:
    return WindowContext("chrome", "Google Chrome", ("web", "page", "tab", "url"))

def _firefox() -> WindowContext:
    return WindowContext("firefox", "Mozilla Firefox", ("web", "page", "tab", "url"))

def _excel() -> WindowContext:
    return WindowContext("excel", "Microsoft Excel", ("spreadsheet", "cells", "formula"))

def _slack() -> WindowContext:
    return WindowContext("slack", "Slack", ("chat", "messages"))

def _discord() -> WindowContext:
    return WindowContext("discord", "Discord", ("chat", "messages"))

def _terminal() -> WindowContext:
    return WindowContext("terminal", "Terminal", ("shell", "command", "stack-trace"))

def _explorer() -> WindowContext:
    return WindowContext("explorer", "File Explorer", ("files", "folders"))

def _generic(label: str = "Unknown") -> WindowContext:
    return WindowContext("generic", label, ())


# --- Rule table --------------------------------------------------------------
# Each rule is (needles, factory). A rule fires when ANY needle is a substring
# of the lower-cased title. Order is significant: place more-specific tokens
# first so e.g. "Visual Studio Code" wins before any generic "studio" hit, and
# "Bambu Studio" matches before a hypothetical bare "Studio" rule could.
_Rule = tuple[tuple[str, ...], Callable[[], WindowContext]]

_RULES: tuple[_Rule, ...] = (
    # Editors / IDEs first — "visual studio code" before any "studio" overlap.
    (("visual studio code", " - vscode", "— vscode"), _vscode),
    # 3D / CAD — pin "bambu studio" early so it never collides with "studio".
    (("bambu studio",), _bambu),
    (("fusion 360", "autodesk fusion"), _fusion360),
    (("freecad",), _freecad),
    (("blender",), _blender),
    # Notes
    (("obsidian",), _obsidian),
    # Browsers — match the trailing app suffix Windows appends.
    (("google chrome",), _chrome),
    (("mozilla firefox",), _firefox),
    # Office
    (("- excel", "— excel", ".xlsx", ".xlsm", "microsoft excel"), _excel),
    # Chat
    (("slack",), _slack),
    (("discord",), _discord),
    # Shells — keep before "explorer" since "windows terminal" is unambiguous.
    (("powershell", "windows terminal", "cmd.exe", "command prompt"), _terminal),
    # File manager — "file explorer" is specific; bare "explorer" is the
    # process name Windows often surfaces for Explorer windows with no path.
    (("file explorer", "windows explorer", "this pc", "quick access"), _explorer),
)


def detect_context(window_title: str | None) -> WindowContext:
    """Map a Windows window title to a :class:`WindowContext`.

    Returns a ``generic`` context with ``app_label="Unknown"`` for empty or
    unrecognised titles. Pure function — no I/O, no globals mutated.
    """
    if not window_title or not window_title.strip():
        return _generic()
    haystack = window_title.lower()
    for needles, factory in _RULES:
        if any(needle in haystack for needle in needles):
            return factory()
    return _generic()
