from __future__ import annotations
import networkx as nx
import pytest

from lexaugraph.codifiability import (
    _PRESCRIPTIVE_DENSITY_PATTERN_7,
    _PRESCRIPTIVE_DENSITY_PATTERN_5,
    _prescriptive_density_tag,
)
from lexaugraph.complexity import _count_matches


def test_prescriptive_density_7_word_pattern_matches_alrc_list():
    text = (
        "The Secretary must approve the application. A person shall not disclose "
        "the record. This action is prohibited without written consent. The "
        "applicant is required to provide evidence. The Minister may only act on "
        "enumerated grounds. This liability cannot be waived."
    )
    count = len(_PRESCRIPTIVE_DENSITY_PATTERN_7.findall(text))
    # must, shall, prohibited, required, may only, cannot be = 6
    # ("shall not" contains "shall" -- not "may not", so counted once for "shall")
    assert count == 6


def test_prescriptive_density_5_word_subset_excludes_may_only_and_cannot_be():
    text = "The Minister may only act on enumerated grounds. This liability cannot be waived."
    count = len(_PRESCRIPTIVE_DENSITY_PATTERN_5.findall(text))
    assert count == 0


def test_prescriptive_density_5_word_subset_matches_core_regdata_words():
    text = "The Secretary must approve. A person shall not disclose. This is prohibited. Evidence is required."
    count = len(_PRESCRIPTIVE_DENSITY_PATTERN_5.findall(text))
    assert count == 4


def test_prescriptive_density_tag_buckets_by_count():
    assert _prescriptive_density_tag(0) == "low"
    assert _prescriptive_density_tag(1) == "low"
    assert _prescriptive_density_tag(2) == "medium"
    assert _prescriptive_density_tag(4) == "medium"
    assert _prescriptive_density_tag(5) == "high"
    assert _prescriptive_density_tag(10) == "high"


from lexaugraph.codifiability import _parse_verification_status  # noqa: E402


def test_parse_verification_status_defaults_to_not_yet_checked():
    assert _parse_verification_status("/akn/au/act/1988/119", {}) == "not_yet_checked"


def test_parse_verification_status_returns_recorded_value():
    data = {"/akn/au/act/1988/119": "spot_checked"}
    assert _parse_verification_status("/akn/au/act/1988/119", data) == "spot_checked"


def test_parse_verification_status_unrecorded_act_defaults_even_with_other_data_present():
    data = {"/akn/au/act/1988/119": "spot_checked"}
    assert _parse_verification_status("/akn/au/act/1999/9", data) == "not_yet_checked"


from lexaugraph.codifiability import (  # noqa: E402
    build_signal1_prompt,
    parse_signal_response,
)


def test_build_signal1_prompt_includes_section_text():
    prompt = build_signal1_prompt("A person who is 18 years or older may apply.")
    assert "A person who is 18 years or older may apply." in prompt


def test_parse_signal_response_strips_markdown_fences_and_parses_json():
    raw = '```json\n{"tag": "high", "reasoning": "clear numeric threshold"}\n```'
    result = parse_signal_response(raw)
    assert result == {"tag": "high", "reasoning": "clear numeric threshold"}


def test_parse_signal_response_parses_plain_json_without_fences():
    raw = '{"tag": "low", "reasoning": "hinges on reasonableness"}'
    result = parse_signal_response(raw)
    assert result == {"tag": "low", "reasoning": "hinges on reasonableness"}


def test_parse_signal_response_returns_none_for_invalid_json():
    assert parse_signal_response("not json at all") is None


def test_parse_signal_response_returns_none_for_invalid_tag_value():
    raw = '{"tag": "very-high", "reasoning": "..."}'
    assert parse_signal_response(raw) is None


def test_parse_signal_response_returns_none_when_reasoning_missing():
    raw = '{"tag": "high"}'
    assert parse_signal_response(raw) is None


from lexaugraph.codifiability import build_signal2_prompt  # noqa: E402


def test_build_signal2_prompt_includes_section_text():
    prompt = build_signal2_prompt("Reasonable steps must be taken in the circumstances.")
    assert "Reasonable steps must be taken in the circumstances." in prompt


from lexaugraph.codifiability import (  # noqa: E402
    _custom_id,
    build_batch_requests,
    submit_batch,
    wait_for_batch,
    fetch_batch_results,
)


def test_custom_id_stays_under_64_chars_for_a_long_node_id():
    long_node_id = "/akn/au/act/1988/119#" + "part-II__dvs-1__sec-" * 3 + "6AA"
    assert len(long_node_id) > 64  # sanity: the raw id itself would already violate the cap
    cid = _custom_id("signal1", long_node_id)
    assert len(cid) <= 64


def test_custom_id_is_deterministic():
    assert _custom_id("signal1", "x") == _custom_id("signal1", "x")


def test_custom_id_differs_by_signal_for_the_same_node():
    assert _custom_id("signal1", "x") != _custom_id("signal2", "x")


def test_build_batch_requests_returns_requests_and_id_map():
    items = [("/akn/au/act/2000/1#sec-1", "Some provision text.")]
    requests, id_map = build_batch_requests("signal1", items, "SYSTEM", lambda t: f"PROMPT: {t}")
    assert len(requests) == 1
    req = requests[0]
    assert req["params"]["system"] == "SYSTEM"
    assert req["params"]["messages"] == [{"role": "user", "content": "PROMPT: Some provision text."}]
    assert id_map[req["custom_id"]] == "/akn/au/act/2000/1#sec-1"


def test_submit_batch_returns_batch_id():
    class _FakeBatch:
        id = "batch-abc"
    class _FakeBatches:
        def create(self, requests):
            return _FakeBatch()
    class _FakeMessages:
        batches = _FakeBatches()
    class _FakeClient:
        messages = _FakeMessages()

    batch_id = submit_batch([{"custom_id": "x", "params": {}}], _FakeClient())
    assert batch_id == "batch-abc"


def test_wait_for_batch_polls_until_ended(monkeypatch):
    class _FakeBatchStatus:
        def __init__(self, status):
            self.processing_status = status
    statuses = iter(["in_progress", "in_progress", "ended"])
    class _FakeBatches:
        def retrieve(self, batch_id):
            return _FakeBatchStatus(next(statuses))
    class _FakeMessages:
        batches = _FakeBatches()
    class _FakeClient:
        messages = _FakeMessages()

    sleeps = []
    monkeypatch.setattr("lexaugraph.codifiability.time.sleep", lambda s: sleeps.append(s))

    wait_for_batch("batch-1", _FakeClient(), poll_interval=1)

    assert sleeps == [1, 1]  # slept before the 2nd and 3rd checks, not after "ended"


def test_fetch_batch_results_maps_custom_id_back_to_node_id_via_id_map():
    class _TextBlock:
        type = "text"
        text = '{"tag": "high", "reasoning": "clear numeric threshold"}'
    class _Message:
        content = [_TextBlock()]
    class _SucceededResult:
        type = "succeeded"
        message = _Message()
    class _Entry:
        def __init__(self, custom_id, result):
            self.custom_id = custom_id
            self.result = result
    class _FakeBatches:
        def results(self, batch_id):
            return [_Entry("hashed-id-1", _SucceededResult())]
    class _FakeMessages:
        batches = _FakeBatches()
    class _FakeClient:
        messages = _FakeMessages()

    id_map = {"hashed-id-1": "/akn/au/act/2000/1#sec-1"}
    results = fetch_batch_results("batch-1", _FakeClient(), id_map)

    assert results == {
        "/akn/au/act/2000/1#sec-1": {"tag": "high", "reasoning": "clear numeric threshold"}
    }


def test_fetch_batch_results_maps_failed_entry_to_none():
    class _ErroredResult:
        type = "errored"
    class _Entry:
        custom_id = "hashed-id-1"
        result = _ErroredResult()
    class _FakeBatches:
        def results(self, batch_id):
            return [_Entry()]
    class _FakeMessages:
        batches = _FakeBatches()
    class _FakeClient:
        messages = _FakeMessages()

    id_map = {"hashed-id-1": "/akn/au/act/2000/1#sec-1"}
    results = fetch_batch_results("batch-1", _FakeClient(), id_map)

    assert results == {"/akn/au/act/2000/1#sec-1": None}
