import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tasks.classify_channels import _parse_response
from tasks.discover_channels import _parse_pre_classify_response
from utils.ai_response import extract_response_text


def test_parse_classification_response_accepts_fenced_json() -> None:
    categories, summary, confidence, signals = _parse_response(
        "```json\n"
        '{"categories":["Financial / Macro"],"summary":"Macro-focused commentary.",'
        '"confidence":0.8,"signals":["title_match"]}\n'
        "```"
    )

    assert categories == ["Financial / Macro"]
    assert summary == "Macro-focused commentary."
    assert confidence == 0.8
    assert signals == ["title_match"]


def test_parse_classification_response_accepts_prefixed_json() -> None:
    categories, summary, confidence, signals = _parse_response(
        "Here is the JSON:\n"
        '{"categories":["Health / Wellness"],"summary":"Wellness content",'
        '"confidence":"0.7","signals":[]}'
    )

    assert categories == ["Health / Wellness"]
    assert summary == "Wellness content"
    assert confidence == 0.7
    assert signals == []


def test_parse_pre_classify_response_accepts_trailing_text() -> None:
    batch = [{"channel_url": "https://rumble.com/c/example"}]
    results = _parse_pre_classify_response(
        '{"results":[{"id":0,"on_topic":false,'
        '"niches":["Prepper / Survival"],"confidence":0.91}]} extra',
        batch,
    )

    assert results == [
        {
            "channel_url": "https://rumble.com/c/example",
            "on_topic": False,
            "niches": ["Prepper / Survival"],
            "confidence": 0.91,
        }
    ]


def test_response_text_falls_back_to_candidate_parts() -> None:
    response = SimpleNamespace(
        text=None,
        candidates=[
            SimpleNamespace(
                content=SimpleNamespace(
                    parts=[
                        SimpleNamespace(text='{"categories":["News / Commentary"]}'),
                    ]
                )
            )
        ],
    )

    assert extract_response_text(response) == '{"categories":["News / Commentary"]}'
