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

"""Nhúng qua API ngoài chuẩn OpenAI (``MOC_EMBED_API=openai``) với máy chủ giả: biến cấu hình, thân yêu cầu
``/embeddings`` (``dimensions``, khóa, tiền tố câu hỏi, che ở lối ra), dò và nhúng thử câu mẫu, số chiều lệch, lỗi,
tên embedder mang số chiều (đổi là nhúng lại), ``make_ai`` ghép với bước viết; mặc định Ollama không đổi."""

from __future__ import annotations

import asyncio
import json

import httpx2
import pytest

from assist_fakes import EMBED_MODEL, FakeOllama
from conftest import FakeChunkIndex
from svc_files.assist import ai as ai_mod
from svc_files.assist.ai import NullAi, OllamaAi, OpenAiChat, OpenAiEmbed, SplitAi, make_ai, query_text
from svc_files.assist.index import ChunkIndexer
from svc_files.assist.meili import embedder_name
from svc_files.config import ConfigError, Settings
from test_assist_chunks import sentences
from test_assist_index import add

URL = "https://nhung.example/openai/v1"
MODEL = "text-embedding-3-small"
KEY = "khoa-gia"  # ngắn, không giống khóa thật: gitleaks quét mọi ref (#436)
BASE = {"MOC_OIDC_ISSUER": "http://kc/realms/moc", "MOC_OIDC_JWKS_URL": "http://unused/jwks",
        "SEAWEEDFS_S3_ACCESS_KEY": "t", "SEAWEEDFS_S3_SECRET_KEY": "t", "HASURA_ADMIN_SECRET": "t",
        "MEILISEARCH_API_KEY": "t"}
API = {**BASE, "MOC_EMBED_API": "openai", "MOC_EMBED_API_URL": URL, "MOC_EMBED_API_MODEL": MODEL}


def run(coro):
    return asyncio.run(coro)


def events(records, name: str) -> list[dict]:
    return [r for r in records if r.get("event") == name]


class FakeEmbedApi:
    """Máy chủ chuẩn OpenAI giả: ``GET /openai/v1/models``; ``POST /openai/v1/embeddings`` trả véc-tơ ``native`` chiều
    (hoặc đúng ``dimensions`` khi ``honor_dims``), theo thứ tự ngược kèm ``index`` như máy chủ được phép làm."""

    def __init__(self, *, native: int = 1536, honor_dims: bool = True, models_status: int = 200,
                 embed_status: int = 200, sleep_s: float = 0.0) -> None:
        self.native = native
        self.honor_dims = honor_dims
        self.models_status = models_status
        self.embed_status = embed_status
        self.sleep_s = sleep_s
        self.reply: dict | None = None
        self.requests: list[httpx2.Request] = []

    def calls(self, name: str) -> list[httpx2.Request]:
        return [r for r in self.requests if r.url.path == f"/openai/v1/{name}"]

    def bodies(self) -> list[dict]:
        return [json.loads(r.content) for r in self.calls("embeddings")]

    async def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if request.url.path == "/openai/v1/models":
            return httpx2.Response(self.models_status, json={"object": "list", "data": [{"id": MODEL}]})
        if self.sleep_s:
            await asyncio.sleep(self.sleep_s)
        if self.embed_status != 200:
            return httpx2.Response(self.embed_status, json={"error": {"message": "lỗi"}})
        if self.reply is not None:
            return httpx2.Response(200, json=self.reply)
        body = json.loads(request.content)
        dims = body.get("dimensions") if self.honor_dims and body.get("dimensions") else self.native
        data = [{"object": "embedding", "index": i, "embedding": [float(len(t)), *([0.5] * (dims - 1))]}
                for i, t in enumerate(body["input"])]
        return httpx2.Response(200, json={"object": "list", "data": data[::-1], "model": body["model"]})


def client(fake: FakeEmbedApi, *, key: str = KEY, dims: int = 1024, send_dims: bool = True,
           probe: bool = True, model: str = MODEL) -> OpenAiEmbed:
    ai = OpenAiEmbed(URL, model, key, transport=httpx2.MockTransport(fake), dims=dims, send_dims=send_dims)
    if probe:
        run(ai.probe())
    return ai


def embed(ai, texts, *, query: bool = False, timeout_s: float = 5.0):
    return run(ai.embed(texts, query=query, timeout_s=timeout_s))


# --- biến cấu hình -------------------------------------------------------------------------------------------------


def test_embeddings_stay_in_ollama_by_default():
    s = Settings.from_env(BASE)
    assert (s.embed_api, s.embed_api_url, s.embed_api_key, s.embed_api_model, s.embed_api_dims) == (
        "ollama", "", "", "", 0)
    assert s.embed_dims == s.ai_embed_dims == 1024
    # MOC_EMBED_API_DIMS chỉ có nghĩa với API ngoài: Ollama vẫn theo MOC_AI_EMBED_DIMS
    assert Settings.from_env({**BASE, "MOC_EMBED_API_DIMS": "256", "MOC_AI_EMBED_DIMS": "768"}).embed_dims == 768
    ai = make_ai(Settings.from_env({**BASE, "MOC_AI_URL": "http://ollama:11434"}))
    assert isinstance(ai, OllamaAi) and (ai.chat_model, ai.embed_model, ai.dims) == (
        "qwen3:1.7b", "qwen3-embedding:0.6b", 1024)
    run(ai.aclose())


def test_external_embedding_settings():
    s = Settings.from_env({**API, "MOC_EMBED_API": " OpenAI ", "MOC_EMBED_API_URL": f" {URL}/ ",
                           "MOC_EMBED_API_KEY": f" {KEY} ", "MOC_EMBED_API_DIMS": " 512 "})
    assert (s.embed_api, s.embed_api_url, s.embed_api_model, s.embed_api_dims, s.embed_dims) == (
        "openai", URL, MODEL, 512, 512)
    assert s.embed_api_key == KEY and KEY not in repr(s)
    s = Settings.from_env({**API, "MOC_EMBED_API_DIMS": "", "MOC_AI_EMBED_DIMS": "1536"})
    assert (s.embed_api_dims, s.embed_dims, s.embed_api_key) == (0, 1536, "")


@pytest.mark.parametrize(("env", "message"), [
    ({"MOC_EMBED_API": "azure"}, "MOC_EMBED_API phải"),
    ({"MOC_EMBED_API": "openai"}, "MOC_EMBED_API_URL"),
    ({**API, "MOC_EMBED_API_URL": "nhung.example/v1"}, "MOC_EMBED_API_URL"),
    ({**API, "MOC_EMBED_API_URL": "ftp://nhung.example/v1"}, "MOC_EMBED_API_URL"),
    # tên mô hình của API ngoài không lấy MOC_AI_EMBED_MODEL (mô hình Ollama tại chỗ)
    ({**API, "MOC_EMBED_API_MODEL": " "}, "MOC_EMBED_API_MODEL"),
    ({**API, "MOC_EMBED_API_MODEL": "a#b"}, "MOC_EMBED_API_MODEL"),
    ({**API, "MOC_EMBED_API_DIMS": "-1"}, "MOC_EMBED_API_DIMS"),
    ({**API, "MOC_EMBED_API_DIMS": "nhiều"}, "Giá trị số"),
])
def test_bad_external_embedding_api_stops_startup(env, message):
    with pytest.raises(ConfigError, match=message):
        Settings.from_env({**BASE, **env})


def test_external_embedding_warnings():
    assert Settings.from_env({**API, "MOC_EMBED_API_KEY": KEY}).warnings() == []
    (warning,) = Settings.from_env({**API, "MOC_EMBED_API_URL": "http://tei:8080/v1"}).warnings()
    assert "MOC_EMBED_API_URL" in warning and "MOC_EMBED_API_KEY" not in warning
    (warning,) = Settings.from_env({**API, "MOC_EMBED_API_URL": "http://tei:8080/v1",
                                    "MOC_EMBED_API_KEY": KEY}).warnings()
    assert "MOC_EMBED_API_KEY" in warning and KEY not in warning
    # nhúng ra ngoài: Ollama chỉ còn giữ mô hình trích yếu và mô hình viết — hai chỗ là đủ
    ai = {**API, "MOC_AI_URL": "http://ollama:11434", "MOC_ASK_MODEL": "qwen3:4b"}
    assert Settings.from_env(ai).warnings() == []
    assert Settings.from_env({**ai, "MOC_EMBED_API": "ollama"}).warnings() != []


# --- yêu cầu, trả lời ----------------------------------------------------------------------------------------------


def test_probe_embeds_a_sample_then_request_and_reply():
    fake = FakeEmbedApi()
    ai = client(fake)
    assert ai.embed_available and not ai.chat_available and ai.embed_model == f"{MODEL}@1024"
    assert fake.bodies() == [{"model": MODEL, "input": ["Mộc"], "dimensions": 1024}]     # nhúng thử lúc dò
    got = embed(ai, ["một", "hai ba"])
    assert got is not None and [v[0] for v in got] == [3.0, 6.0] and all(len(v) == 1024 for v in got)
    assert ai.embed_error is None
    assert fake.bodies()[-1] == {"model": MODEL, "input": ["một", "hai ba"], "dimensions": 1024}
    assert all(r.headers["authorization"] == f"Bearer {KEY}" for r in fake.requests)
    run(ai.probe())                                     # đã sẵn sàng: chỉ GET /models, không nhúng thử lại
    assert len(fake.calls("embeddings")) == 2 and len(fake.calls("models")) == 2


def test_without_dims_or_key_nothing_extra_is_sent():
    fake = FakeEmbedApi(native=768)
    ai = client(fake, key="", dims=768, send_dims=False)
    assert embed(ai, ["x"]) is not None
    assert all("dimensions" not in b for b in fake.bodies())
    assert all("authorization" not in r.headers for r in fake.requests)


def test_query_prefix_and_masking_at_egress():
    fake = FakeEmbedApi()
    ai = client(fake, model="Qwen3-Embedding-0.6B")
    assert embed(ai, ["Hạn nộp?"], query=True) is not None
    assert fake.bodies()[-1]["input"] == [query_text("Qwen3-Embedding-0.6B", "Hạn nộp?")]
    assert embed(ai, ["Gọi 0912345678 hoặc a.b@truong.edu.vn"]) is not None
    sent = fake.bodies()[-1]["input"][0]
    assert "0912345678" not in sent and "a.b@truong.edu.vn" not in sent


def test_wrong_dimensions_turn_embedding_off_with_a_clear_error(log_records):
    """Máy chủ bỏ qua ``dimensions`` (hoặc MOC_AI_EMBED_DIMS sai): biết ngay lúc dò, tắt nhúng tới khi sửa biến."""
    fake = FakeEmbedApi(native=1536, honor_dims=False)
    ai = client(fake)
    assert not ai.embed_available
    (err,) = events(log_records, "office.assist.embed_dims_mismatch")
    assert (err["model"], err["dims"], err["expected"], err["where"]) == (MODEL, 1536, 1024, "external")
    assert "MOC_EMBED_API_DIMS" in err["message"] and "MOC_AI_EMBED_DIMS" in err["message"]
    calls = len(fake.calls("embeddings"))
    assert embed(ai, ["x"]) is None and ai.embed_error == "model_unavailable"
    assert len(fake.calls("embeddings")) == calls                                     # không gọi nữa
    run(ai.probe())
    assert not ai.embed_available and len(events(log_records, "office.assist.embed_dims_mismatch")) == 1


def test_wrong_dimensions_found_on_the_first_embedding_when_the_sample_failed():
    fake = FakeEmbedApi(native=1536, honor_dims=False, embed_status=503)
    ai = client(fake)
    assert ai.embed_available                           # câu mẫu lỗi tạm: chưa biết số chiều
    fake.embed_status = 200
    assert embed(ai, ["x"]) is None and ai.embed_error == "dims_mismatch"
    assert ai.embed_error in ai_mod.TRANSIENT and not ai.embed_available


def test_errors_and_readiness(log_records):
    for status in (401, 403, 404):                      # khóa sai, hết quyền, sai tên mô hình
        assert not client(FakeEmbedApi(embed_status=status)).embed_available        # câu mẫu lúc dò
        fake = FakeEmbedApi()
        ai = client(fake)
        fake.embed_status = status
        assert embed(ai, ["x"]) is None and ai.embed_error == f"http {status}" and not ai.embed_available
        assert embed(ai, ["x"]) is None and ai.embed_error == "model_unavailable"   # tới lượt dò sau
    for status in (429, 503):                           # lỗi tạm: vẫn dùng, vòng nền thử lại sau
        fake = FakeEmbedApi()
        ai = client(fake)
        fake.embed_status = status
        assert embed(ai, ["x"]) is None and ai.embed_error in ai_mod.TRANSIENT and ai.embed_available
    for status in (401, 500):
        assert not client(FakeEmbedApi(models_status=status)).embed_available
    fake = FakeEmbedApi()
    slow = client(fake)
    fake.sleep_s = 0.5
    assert embed(slow, ["x"], timeout_s=0.1) is None and slow.embed_error == "timeout"
    fake = FakeEmbedApi()
    ai = client(fake)
    for reply in ({"data": []}, {"data": [{"embedding": [1.0, "x"]}]}, {"object": "list"}):
        fake.reply = reply
        assert embed(ai, ["x"]) is None and ai.embed_error == "bad_output" and ai.embed_available
    cold = client(FakeEmbedApi(), probe=False)
    assert embed(cold, ["x"]) is None and cold.embed_error == "model_unavailable"

    async def unreachable(request):
        raise httpx2.ConnectError("không tới được")

    gone = OpenAiEmbed(URL, MODEL, KEY, transport=httpx2.MockTransport(unreachable))
    run(gone.probe())
    assert not gone.embed_available
    down = events(log_records, "office.assist.ai_unavailable")
    assert down[-1]["reason"] == "unreachable" and all(e["kind"] == "embed" for e in down)
    assert all(KEY not in json.dumps(r) for r in log_records)      # khóa không bao giờ vào nhật ký


# --- số chiều trong tên embedder: đường nhúng lại sẵn có --------------------------------------------------------


def test_dimension_is_part_of_the_embedder_name():
    names = {embedder_name(client(FakeEmbedApi(), dims=d, probe=False).embed_model) for d in (256, 1024)}
    assert names == {"emb_text_embedding_3_small_256", "emb_text_embedding_3_small_1024"}
    assert embedder_name(EMBED_MODEL) not in names      # chuyển từ Ollama sang: embedder mới, nhúng lại cả chỉ mục


def test_chunk_indexer_embeds_through_the_external_api(hasura):
    index = FakeChunkIndex()
    add(hasura, pages=(sentences("MOT", 3),))
    fake = FakeEmbedApi()
    indexer = ChunkIndexer(index, hasura, client(fake, dims=256), dims=256)
    run(indexer.sync_once())
    assert index.settings[0]["embedder"] == "emb_text_embedding_3_small_256" and index.settings[0]["dims"] == 256
    assert run(indexer.embed_once()) == len(index.docs)
    for doc in index.docs.values():
        assert doc["embed_model"] == f"{MODEL}@256"
        assert len(doc["_vectors"]["emb_text_embedding_3_small_256"]["embeddings"]) == 256
    # đổi MOC_EMBED_API_DIMS: tên khác, embedder cũ bị bỏ, mọi đoạn chờ nhúng lại
    again = ChunkIndexer(index, hasura, client(FakeEmbedApi(), dims=512), dims=512)
    run(again.sync_once())
    assert index.settings[-1]["embedder"] == "emb_text_embedding_3_small_512"
    assert "emb_text_embedding_3_small_256" in index.settings[-1]["removed"]
    assert run(again.embed_once()) == len(index.docs)


# --- ghép với bước viết ----------------------------------------------------------------------------------------------


def test_make_ai_external_embeddings():
    local = {**API, "MOC_AI_URL": "http://ollama:11434", "MOC_EMBED_API_KEY": KEY, "MOC_EMBED_API_DIMS": "256"}
    got = make_ai(Settings.from_env(local))
    assert isinstance(got, SplitAi) and isinstance(got.embedder, OpenAiEmbed) and isinstance(got.writer, OllamaAi)
    assert (got.embed_model, got.chat_model, got.chat_where) == (f"{MODEL}@256", "qwen3:1.7b", "local")
    assert got.writer.embed_model is None                   # Ollama không dò, không nạp mô hình nhúng
    assert (got.embedder.dims, got.embedder.send_dims) == (256, True)
    run(got.aclose())
    got = make_ai(Settings.from_env({**API, "MOC_AI_URL": "", "MOC_AI_EMBED_DIMS": "1536"}))
    assert isinstance(got.writer, NullAi) and (got.embedder.dims, got.embedder.send_dims) == (1536, False)
    run(got.aclose())
    both = {**local, "MOC_ASK_API": "openai", "MOC_ASK_API_URL": "https://viet.example/v1",
            "MOC_ASK_MODEL": "mo-hinh-ngoai"}
    got = make_ai(Settings.from_env(both))
    assert isinstance(got.writer, OpenAiChat) and got.chat_where == "external"
    run(got.aclose())


def test_split_ai_embeds_externally_and_writes_locally():
    remote, local = FakeEmbedApi(), FakeOllama()
    writer = OllamaAi("http://ollama:11434", "qwen3:1.7b", None, transport=httpx2.MockTransport(local))
    ai = SplitAi(client(remote), writer)
    run(writer.probe())
    assert ai.embed_available and ai.chat_available and ai.chat_where == "local"
    assert embed(ai, ["x"]) is not None and ai.embed_error is None
    assert local.calls("/api/embed") == [] and len(remote.calls("embeddings")) == 2
    run(ai.aclose())
