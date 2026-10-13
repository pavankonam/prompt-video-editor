"""Planner tests with a fake Ollama, so they run without a model installed."""

import json

import pytest

from editor import llm, planner
from editor.plan import PlanError
from tests.test_parsing import lib, simple


class FakeResponse:
    def __init__(self, payload, status=200):
        self.status_code = status
        self.ok = status < 400
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        return self._payload


def fake_ollama(monkeypatch, answers):
    """Make requests to Ollama return the given plans in order."""
    calls = []

    def post(url, json=None, timeout=None):
        calls.append(json)
        plan = answers[min(len(calls), len(answers)) - 1]
        return FakeResponse({"message": {"content": __import__("json").dumps({"steps": plan})}})

    monkeypatch.setattr(llm, "is_available", lambda host=None: True)
    monkeypatch.setattr(llm.requests, "post", post)
    return calls


GOOD = [
    {"type": "clip", "source": "video1", "start": "2:34", "end": "2:55"},
    {"type": "image", "source": "photo1", "duration": "4"},
    {"type": "clip", "source": "video1", "start": "5:12", "end": "5:50"},
    {"type": "clip", "source": "video2", "start": "start", "end": "end"},
]


def test_llm_plan_is_used(monkeypatch):
    calls = fake_ollama(monkeypatch, [GOOD])
    result = planner.make_plan("anything", lib(), engine="llm", model="qwen2.5:7b")
    assert result.engine.startswith("llm")
    assert simple(result.steps)[1] == ("image", "photo1", 0, 4)
    assert "video1 (video, length 6:10" in calls[0]["messages"][0]["content"]


def test_llm_bad_plan_gets_one_retry(monkeypatch):
    bad = [{"type": "clip", "source": "video9", "start": "0:00", "end": "0:05"}]
    calls = fake_ollama(monkeypatch, [bad, GOOD])
    result = planner.make_plan("anything", lib(), engine="llm")
    assert len(calls) == 2
    assert "video9" in calls[1]["messages"][-1]["content"]
    assert len(result.steps) == 4


def test_auto_falls_back_to_rules_when_llm_is_wrong(monkeypatch):
    bad = [{"type": "clip", "source": "video9"}]
    fake_ollama(monkeypatch, [bad, bad])
    result = planner.make_plan("from video2 take 0:01 to 0:03", lib(), engine="auto")
    assert result.engine == "rules"
    assert simple(result.steps) == [("clip", "video2", 1, 3)]


def test_llm_only_reports_when_ollama_is_off(monkeypatch):
    monkeypatch.setattr(llm, "is_available", lambda host=None: False)
    with pytest.raises(PlanError) as e:
        planner.make_plan("x", lib(), engine="llm")
    assert "ollama" in str(e.value).lower()
