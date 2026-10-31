# Copyright 2026 Signet Team
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# SPDX-License-Identifier: Apache-2.0

"""Bước ý định bằng mô hình (assist/intent.py): mô hình chọn đường, bộ luật là dự phòng."""

from __future__ import annotations

import json

import pytest

from assist_fakes import FakeOllama, good_answer, ollama
from svc_files.assist import intent
from test_assist_api import D88, ask, asking, demo  # noqa: F401 (asking là fixture)

ON = {"MOC_ASK_INTENT": "true"}


def says(y_dinh: str, cau_hoi: str = "") -> str:
    return json.dumps({"y_dinh": y_dinh, "cau_hoi": cau_hoi}, ensure_ascii=False)


def model(intent_reply: str, answer: str | None = None):
    """Ollama giả: lời dặn của bước ý định → ``intent_reply``; lượt viết câu trả lời → ``answer``."""
    async def reply(request):
        system = json.loads(request.content)["messages"][0]["content"]
        return intent_reply if system == intent.SYSTEM else (answer or good_answer())
    return reply


def intent_calls(fake: FakeOllama) -> int:
    return sum(c["messages"][0]["content"] == intent.SYSTEM for c in fake.calls("/api/chat"))


def routed(env, question: str, **body) -> dict:
    r = ask(env, env.token(), question=question, **body)
    assert r.status_code == 200, r.text
    return r.json()


# --- đọc đầu ra của mô hình ----------------------------------------------------------------------------------------


def test_every_intent_maps_to_a_route():
    for y_dinh, (name, _) in intent.INTENTS.items():
        got = intent.parse(says(y_dinh, "x"), "x", None, "vi", masked=False)
        assert got is not None and got.route.name == name and got.route.reason.startswith("llm:")
    assert set(intent.FORMAT["properties"]["y_dinh"]["enum"]) == set(intent.INTENTS)


@pytest.mark.parametrize("content", ["", "không phải JSON", '{"y_dinh": "giai_toan", "cau_hoi": "x"}',
                                     '{"y_dinh": "tra_van_ban"}', '["tra_van_ban"]', None])
def test_a_bad_reply_falls_back(content):
    assert intent.parse(content, "x", None, "vi", masked=False) is None


def test_the_rewrite_is_used_only_for_a_follow_up_without_masked_text():
    q, prev, full = "Còn điều 5 thì sao?", "Quy chế 06/2026 điều 4 nói gì?", "Quy chế 06/2026 điều 5 nói gì?"
    assert intent.parse(says("tra_van_ban", full), q, prev, "vi", masked=False).rewritten == full
    assert intent.parse(says("tra_van_ban", full), q, None, "vi", masked=False).rewritten is None   # không có câu trước
    assert intent.parse(says("tra_van_ban", full), q, prev, "vi", masked=True).rewritten is None    # có số bị che
    assert intent.parse(says("tra_van_ban", q), q, prev, "vi", masked=False).rewritten is None      # chép nguyên
    assert intent.parse(says("tra_van_ban", "x" * 501), q, prev, "vi", masked=False).rewritten is None


# --- qua API ------------------------------------------------------------------------------------------------------


def test_the_model_sends_an_off_topic_question_away_without_search(asking):
    fake = FakeOllama(reply=model(says("ngoai_pham_vi", "Thời tiết")))
    env = asking(env=ON, passages=demo(), ai=ollama(fake))
    body = routed(env, "Thời tiết")
    assert (body["route"], body["route_reason"]) == ("ngoai_pham_vi", "llm:ngoai-pham-vi")
    assert env.retriever.calls == [] and intent_calls(fake) == 1


def test_the_model_routes_a_greeting_to_the_intro(asking):
    fake = FakeOllama(reply=model(says("hoi_ve_tro_ly", "Em giúp được gì cho anh?")))
    env = asking(env=ON, passages=demo(), ai=ollama(fake))
    body = routed(env, "Em giúp được gì cho anh?")
    assert (body["route"], body["route_reason"]) == ("gioi_thieu", "llm:lam-duoc-gi")
    assert body["sources"][0]["path"].endswith("gioi_thieu/vi.md#lam-duoc-gi")


def test_extract_then_generate_asks_the_model_for_the_route_once(asking):
    fake = FakeOllama(reply=model(says("tra_van_ban", "Điều kiện xét học bổng là gì?")))
    env = asking(env=ON, passages=demo(), ai=ollama(fake))
    first = routed(env, "Điều kiện xét học bổng là gì?")
    second = routed(env, "Điều kiện xét học bổng là gì?", mode="generate", ask_id=first["ask_id"])
    assert first["route_reason"] == second["route_reason"] == "llm:tra-van-ban"
    assert second["answer"]["source"] == "model"
    assert intent_calls(fake) == 1


def test_a_bad_model_reply_falls_back_to_the_rules(asking):
    fake = FakeOllama(reply=model("không phải JSON"))
    env = asking(env=ON, passages=demo(), ai=ollama(fake))
    body = routed(env, "Bạn làm được gì?")
    assert (body["route"], body["route_reason"]) == ("gioi_thieu", "kw:lam-duoc-gi")


def test_the_model_rewrites_a_follow_up(asking):
    full = "Điều kiện xét học bổng khuyến khích học tập về điểm rèn luyện là gì?"
    fake = FakeOllama(reply=model(says("tra_van_ban", full)))
    env = asking(env=ON, passages=demo(), ai=ollama(fake))
    body = routed(env, "Còn điểm rèn luyện thì sao?", previous="Điều kiện xét học bổng khuyến khích học tập là gì?")
    assert body["rewritten"] == full and env.retriever.calls[0]["question"] == full


def test_a_question_inside_one_document_skips_the_intent_step(asking):
    fake = FakeOllama(reply=model(says("ngoai_pham_vi", "x")))
    env = asking(env=ON, passages=demo(), ai=ollama(fake))
    body = routed(env, "Văn bản này yêu cầu gì?", document_id=D88)
    assert body["route"] == "van_ban" and intent_calls(fake) == 0


def test_without_a_model_the_rules_route(asking):
    env = asking(env=ON, passages=demo())
    assert routed(env, "Bạn làm được gì?")["route_reason"] == "kw:lam-duoc-gi"
