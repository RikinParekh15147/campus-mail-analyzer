import json
from campusmail.summary_api import APIEnhancer


def test_api_enhancer_sends_structured_facts_and_decodes_json_only():
    calls = []

    def post(url, **kwargs):
        calls.append((url, kwargs))

        class Response:
            def raise_for_status(self):
                pass

            def json(self):
                return {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "items": [
                                            {
                                                "id": "one",
                                                "summary": "Assignment due 2026-10-25",
                                            }
                                        ]
                                    }
                                )
                            }
                        }
                    ]
                }

        return Response()

    enhancer = APIEnhancer(
        "https://provider.example/v1/chat/completions",
        "example-model",
        "test-key",
        post,
    )
    result = enhancer(
        [
            {
                "id": "one",
                "title": "Assignment",
                "date": "2026-10-25",
                "evidence_ids": ["source1"],
            }
        ]
    )
    assert result[0]["id"] == "one"
    assert calls[0][1]["headers"]["Authorization"] == "Bearer test-key"
    assert "source1" in calls[0][1]["json"]["messages"][1]["content"]


def test_api_enhancer_rejects_non_https_endpoints():
    import pytest

    with pytest.raises(ValueError):
        APIEnhancer("http://example.test", "model", "key")
