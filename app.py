"""Prompt Video Editor: web interface.

Run:  python app.py   then open http://127.0.0.1:7860
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import gradio as gr

from editor import llm
from editor.media import build_library, MediaItem
from editor.plan import PlanError, Step, summarize, total_duration, validate
from editor.planner import make_plan
from editor.render import render
from editor.timecode import fmt

ROOT = Path(__file__).resolve().parent
OUTPUTS = ROOT / "outputs"
OUTPUTS.mkdir(exist_ok=True)

EXAMPLE = ("From video1 take 2:34 to 2:55 and 5:12 to 5:50. "
           "Then combine clip 1, the picture for 4 seconds, clip 2, and finally video2.")
TIMELINE_HEADERS = ["#", "Type", "What", "Length", "Position in final video"]
FILE_HEADERS = ["Name to use", "Type", "Original file", "Length", "Size", "Audio"]


def _library_from_state(state) -> list[MediaItem]:
    return [MediaItem(**d) for d in (state or [])]


def _plan_to_json(steps: list[Step]) -> str:
    out = []
    for s in steps:
        if s.type == "image":
            out.append({"type": "image", "source": s.source, "duration": f"{s.duration:g}"})
        else:
            out.append({"type": "clip", "source": s.source, "start": fmt(s.start), "end": fmt(s.end)})
    return json.dumps(out, indent=2)


def on_upload(files):
    if not files:
        return [], [], gr.update(choices=[], value=None), "Upload videos and photos to begin."
    paths = [f if isinstance(f, str) else f.name for f in files]
    try:
        library = build_library(paths)
    except RuntimeError as e:
        return [], [], gr.update(choices=[], value=None), f"**Error:** {e}"
    rows = [[m.name, m.kind, m.original, fmt(m.duration) if m.kind == "video" else "photo",
             f"{m.width}x{m.height}", "yes" if m.has_audio else "no"] for m in library]
    skipped = len(paths) - len(library)
    msg = f"Loaded {len(library)} file(s). Refer to them by the names in the first column."
    if skipped:
        msg += f" Skipped {skipped} file(s) that are not videos or photos."
    names = [m.name for m in library]
    return ([m.to_dict() for m in library], rows,
            gr.update(choices=names, value=names[0] if names else None), msg)


def on_preview(name, state):
    item = next((m for m in _library_from_state(state) if m.name == name), None)
    if item is None:
        return gr.update(value=None, visible=True), gr.update(value=None, visible=False)
    if item.kind == "video":
        return gr.update(value=item.path, visible=True), gr.update(value=None, visible=False)
    return gr.update(value=None, visible=False), gr.update(value=item.path, visible=True)


def on_plan(prompt, engine, model, state):
    library = _library_from_state(state)
    engine_key = {"Auto (local LLM if running)": "auto", "Local LLM only": "llm",
                  "Offline rules only": "rules"}[engine]
    try:
        result = make_plan(prompt, library, engine=engine_key, model=model.strip() or llm.DEFAULT_MODEL)
    except PlanError as e:
        return "", [], "**Could not make a plan:**\n\n" + "\n".join(f"* {x}" for x in e.errors)
    status = (f"Plan made with **{result.engine}**. Total length **{fmt(total_duration(result.steps))}**. "
              "Check the timeline, edit the JSON if needed, then press Render.")
    if result.notes:
        status += "\n\n" + "\n".join(f"* {n}" for n in result.notes)
    return _plan_to_json(result.steps), summarize(result.steps), status


def on_plan_edit(plan_json, state):
    """Refresh the timeline when the JSON is edited by hand."""
    try:
        steps = validate(json.loads(plan_json or "[]"), _library_from_state(state))
        return summarize(steps)
    except (json.JSONDecodeError, PlanError):
        return gr.update()


def on_render(plan_json, state, progress=gr.Progress()):
    library = _library_from_state(state)
    try:
        raw = json.loads(plan_json or "[]")
        steps = validate(raw, library)
    except json.JSONDecodeError as e:
        return None, f"**The plan JSON is not valid:** {e}"
    except PlanError as e:
        return None, "**Fix the plan first:**\n\n" + "\n".join(f"* {x}" for x in e.errors)
    out = OUTPUTS / f"edit_{time.strftime('%Y%m%d_%H%M%S')}.mp4"
    try:
        render(steps, library, out, progress=lambda f, d: progress(f, desc=d))
    except RuntimeError as e:
        return None, f"**Render failed:**\n\n```\n{e}\n```"
    return str(out), f"Done. Saved to `{out.relative_to(ROOT)}` ({fmt(total_duration(steps))} long)."


def llm_status() -> str:
    if llm.is_available():
        models = llm.installed_models()
        shown = ", ".join(models) if models else "no models pulled yet"
        return f"Local LLM: Ollama is running ({shown})."
    return "Local LLM: Ollama is not running, so the offline rule parser will be used."


with gr.Blocks(title="Prompt Video Editor") as demo:
    gr.Markdown("# Prompt Video Editor\nUpload videos and photos, describe the edit in plain English, "
                "check the plan, and render one combined video. Everything runs on your computer for free.")
    library_state = gr.State([])

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("### 1. Upload")
            uploads = gr.File(label="Videos and photos", file_count="multiple",
                              file_types=["video", "image"])
            upload_msg = gr.Markdown("Upload videos and photos to begin.")
            files_table = gr.Dataframe(headers=FILE_HEADERS, interactive=False, wrap=True)
            preview_pick = gr.Dropdown(label="Preview an uploaded file", choices=[])
            preview_video = gr.Video(label="Preview", interactive=False)
            preview_image = gr.Image(label="Preview", interactive=False, visible=False)

        with gr.Column(scale=1):
            gr.Markdown("### 2. Describe the edit")
            prompt = gr.Textbox(label="Instruction", lines=4, value=EXAMPLE)
            with gr.Row():
                engine = gr.Radio(["Auto (local LLM if running)", "Local LLM only", "Offline rules only"],
                                  value="Auto (local LLM if running)", label="Understanding engine")
                model = gr.Textbox(label="Ollama model", value=llm.DEFAULT_MODEL)
            llm_info = gr.Markdown(llm_status())
            plan_btn = gr.Button("Make plan", variant="primary")
            plan_msg = gr.Markdown()
            timeline = gr.Dataframe(headers=TIMELINE_HEADERS, interactive=False, label="Timeline")
            plan_json = gr.Code(label="Plan (you can edit this)", language="json", interactive=True)

            gr.Markdown("### 3. Render")
            render_btn = gr.Button("Render video", variant="primary")
            render_msg = gr.Markdown()
            result_video = gr.Video(label="Result", interactive=False)

    uploads.change(on_upload, uploads, [library_state, files_table, preview_pick, upload_msg])
    preview_pick.change(on_preview, [preview_pick, library_state], [preview_video, preview_image])
    plan_btn.click(on_plan, [prompt, engine, model, library_state], [plan_json, timeline, plan_msg])
    plan_json.blur(on_plan_edit, [plan_json, library_state], timeline)
    render_btn.click(on_render, [plan_json, library_state], [result_video, render_msg])
    demo.load(llm_status, None, llm_info)


if __name__ == "__main__":
    demo.queue().launch(
        server_name=os.environ.get("PVE_HOST", "127.0.0.1"),
        server_port=int(os.environ.get("PVE_PORT", "7860")),
        inbrowser=os.environ.get("PVE_NO_BROWSER") is None,
        allowed_paths=[str(OUTPUTS)],
    )
