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
import pathlib

import pytest

from assist_fakes import FakeOllama, good_answer, ollama
from svc_files.assist import intent
from test_assist_api import D88, ask, asking, demo  # noqa: F401 (asking là fixture)

ON = {"MOC_ASK_INTENT": "true"}
GUIDES = str(pathlib.Path(__file__).resolve().parents[3] / "docs" / "huong-dan")


def says(y_dinh: str, cau_hoi: str = "", *, can_cau_truoc: bool = False) -> str:
    return json.dumps({"y_dinh": y_dinh, "can_cau_truoc": can_cau_truoc, "cau_hoi": cau_hoi}, ensure_ascii=False)


def model(intent_reply: str, answer: str | None = None, *, with_previous: str | None = None):
    """Ollama giả: lời dặn của bước ý định → ``intent_reply`` (lượt có <cau_truoc>: ``with_previous`` nếu có); lượt
    viết câu trả lời → ``answer``."""
    async def reply(request):
        sent = json.loads(request.content)["messages"]
        if sent[0]["content"] != intent.SYSTEM:
            return answer or good_answer()
        return with_previous if with_previous and "<cau_truoc>" in sent[1]["content"] else intent_reply
    return reply


def intent_calls(fake: FakeOllama) -> list[str]:
    return [c["messages"][1]["content"] for c in fake.calls("/api/chat")
            if c["messages"][0]["content"] == intent.SYSTEM]


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


def test_the_model_says_when_a_question_needs_the_previous_one():
    assert intent.parse(says("tra_van_ban", "x", can_cau_truoc=True), "x", None, "vi", masked=False).needs_previous
    assert not intent.parse(says("huong_dan", "x"), "x", None, "vi", masked=False).needs_previous
    assert not intent.parse('{"y_dinh": "huong_dan", "cau_hoi": "x"}', "x", None, "vi", masked=False).needs_previous


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
    assert env.retriever.calls == [] and len(intent_calls(fake)) == 1


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
    assert len(intent_calls(fake)) == 1


def test_a_bad_model_reply_falls_back_to_the_rules(asking):
    fake = FakeOllama(reply=model("không phải JSON"))
    env = asking(env=ON, passages=demo(), ai=ollama(fake))
    body = routed(env, "Bạn làm được gì?")
    assert (body["route"], body["route_reason"]) == ("gioi_thieu", "kw:lam-duoc-gi")


def test_the_model_rewrites_a_follow_up_in_a_second_turn_with_the_previous_question(asking):
    full = "Điều kiện xét học bổng khuyến khích học tập về điểm rèn luyện là gì?"
    q = "Còn điểm rèn luyện thì sao?"
    fake = FakeOllama(reply=model(says("chua_ro", q, can_cau_truoc=True), with_previous=says("tra_van_ban", full)))
    env = asking(env=ON, passages=demo(), ai=ollama(fake))
    body = routed(env, q, previous="Điều kiện xét học bổng khuyến khích học tập là gì?")
    assert body["rewritten"] == full and env.retriever.calls[0]["question"] == full
    assert body["route_reason"] == "llm:tra-van-ban"
    first, second = intent_calls(fake)
    assert "<cau_truoc>" not in first and "<cau_truoc>" in second


def test_a_standalone_question_is_classified_without_the_previous_one(asking):
    # câu trước về công văn không kéo câu mới về văn bản: lượt duy nhất không có <cau_truoc>
    fake = FakeOllama(reply=model(says("huong_dan", "Nộp đơn nghỉ phép ở đâu?")))
    env = asking(env={**ON, "MOC_ASK_GUIDE_DIR": GUIDES}, passages=demo(), ai=ollama(fake))
    body = routed(env, "Nộp đơn nghỉ phép ở đâu?", previous="Công văn 131/ĐT-ĐHM yêu cầu những gì?")
    assert (body["route"], body["route_reason"], body["rewritten"]) == ("huong_dan", "llm:huong-dan", None)
    (only,) = intent_calls(fake)
    assert "<cau_truoc>" not in only


def test_a_document_question_with_no_passage_is_answered_from_the_user_guide(asking):
    fake = FakeOllama(reply=model(says("tra_van_ban", "Nộp đơn nghỉ phép ở đâu?")))
    env = asking(env={**ON, "MOC_ASK_GUIDE_DIR": GUIDES}, passages=[], ai=ollama(fake))
    body = routed(env, "Nộp đơn nghỉ phép ở đâu?")
    assert (body["route"], body["route_reason"]) == ("huong_dan", "khong-thay-van-ban")
    assert body["sources"] and body["sources"][0]["kind"] == "guide"


def test_what_did_i_just_ask_is_answered_from_the_previous_question(asking):
    said = "Bạn vừa hỏi tôi: “hello em”."
    q = "anh vừa hỏi em cái gì"
    fake = FakeOllama(reply=model(says("hoi_cau_truoc", q, can_cau_truoc=True),
                                  json.dumps({"du_can_cu": True, "tra_loi": said}, ensure_ascii=False)))
    env = asking(env=ON, passages=demo(), ai=ollama(fake))
    first = routed(env, q, previous="hello em")
    assert (first["route"], first["route_reason"], first["status"]) == ("gioi_thieu", "llm:cau-truoc", "answered")
    assert first["answer"] == {"text": "Câu hỏi trước của bạn là: “hello em”.", "source": "fixed", "model": None}
    assert env.retriever.calls == [] and first["sources"] == []
    (only,) = intent_calls(fake)                # không gọi lượt hai kèm câu trước
    assert "<cau_truoc>" not in only
    second = routed(env, q, previous="hello em", mode="generate", ask_id=first["ask_id"])
    assert second["answer"] == {"text": said, "source": "model", "model": second["answer"]["model"]}
    alone = routed(env, q)
    assert alone["answer"]["text"].startswith("Đây là câu hỏi đầu tiên của bạn")


def test_a_question_inside_one_document_skips_the_intent_step(asking):
    fake = FakeOllama(reply=model(says("ngoai_pham_vi", "x")))
    env = asking(env=ON, passages=demo(), ai=ollama(fake))
    body = routed(env, "Văn bản này yêu cầu gì?", document_id=D88)
    assert body["route"] == "van_ban" and intent_calls(fake) == []


def test_without_a_model_the_rules_route(asking):
    env = asking(env=ON, passages=demo())
    assert routed(env, "Bạn làm được gì?")["route_reason"] == "kw:lam-duoc-gi"
