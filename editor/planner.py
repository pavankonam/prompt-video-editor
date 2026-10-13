"""Chooses the engine (local LLM or rules), then validates the plan."""

from __future__ import annotations

from dataclasses import dataclass, field

from . import llm, rules
from .media import MediaItem
from .plan import PlanError, Step, validate


@dataclass
class PlanResult:
    steps: list[Step]
    raw: list[dict]
    engine: str
    notes: list[str] = field(default_factory=list)


def make_plan(prompt: str, library: list[MediaItem], engine: str = "auto",
              model: str = llm.DEFAULT_MODEL, host: str = llm.DEFAULT_HOST) -> PlanResult:
    """engine: "auto" (LLM if Ollama is running, else rules), "llm" or "rules"."""
    if not library:
        raise PlanError(["Upload at least one video or photo first."])
    if not prompt or not prompt.strip():
        raise PlanError(["Type an instruction describing the edit."])

    notes: list[str] = []
    if engine in ("auto", "llm"):
        if llm.is_available(host):
            try:
                return _plan_with_llm(prompt, library, model, host)
            except llm.LLMUnavailable as e:
                if engine == "llm":
                    raise PlanError([str(e)])
                notes.append(f"{e} Used the offline rule parser instead.")
            except (PlanError, ValueError) as e:
                if engine == "llm":
                    raise PlanError(getattr(e, "errors", [str(e)]))
                notes.append("The LLM plan had problems, so the offline rule parser was used instead.")
        else:
            if engine == "llm":
                raise PlanError([f"Ollama is not running at {host}. Start the Ollama app or run: ollama serve"])
            notes.append("Ollama is not running, so the offline rule parser was used.")

    try:
        raw, rule_notes = rules.parse(prompt, library)
    except ValueError as e:
        raise PlanError([str(e)])
    steps = validate(raw, library)
    return PlanResult(steps, raw, "rules", notes + rule_notes)


def _plan_with_llm(prompt, library, model, host) -> PlanResult:
    raw = llm.ask(prompt, library, model=model, host=host)
    try:
        return PlanResult(validate(raw, library), raw, f"llm ({model})")
    except PlanError as e:
        # One retry, telling the model exactly what was wrong
        raw = llm.ask(prompt, library, model=model, host=host, feedback="\n".join(e.errors))
        return PlanResult(validate(raw, library), raw, f"llm ({model})",
                          ["The first LLM plan had errors and was corrected automatically."])
