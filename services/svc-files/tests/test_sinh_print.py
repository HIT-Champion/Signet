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

"""In một dòng của bảng sinh theo mẫu in (#586, #594): thoát HTML, bộ tải URL chỉ nhận data:, token của người gọi
tới PostgREST, dòng của đơn vị khác ra 404."""

from __future__ import annotations

import time
import uuid

import httpx2
import pytest
from conftest import TENANT_A, FakeHasura
from fastapi.testclient import TestClient

from svc_files import sinh_print
from svc_files.app import create_app

TENANT_B = uuid.UUID("6f1c0d2e-0000-4000-8000-00000000000b")
TEMPLATE = "# Phiếu yêu cầu\n\nTiêu đề: {{tieu_de}}\nHạn: {{han}}\nGhi chú: {{khong_co}}\n\nNội dung: {{noi_dung}}"
ROW = {"id": 5, "tieu_de": "Máy in phòng 204", "han": "2026-11-05", "noi_dung": "Hỏng khay giấy",
       "created_at": "2026-11-04T17:30:00+00:00"}


class TenantHasura(FakeHasura):
    async def admin(self, query: str, variables: dict, headers: dict | None = None) -> dict:
        if "DonViIn" not in query:
            return await super().admin(query, variables, headers)
        self._check()
        self.admin_queries.append(query)
        tenant = {"name": "Trường CNTT & TT", "parent_name": "Đại học Mẫu", "place_name": "Hà Nội"}
        return {"core_tenants_by_pk": tenant}


class FakeRest:
    """PostgREST giả: mẫu 1 và dòng 5 của bảng yeu_cau chỉ thấy với token của đơn vị A (RLS)."""

    def __init__(self, token_a: str) -> None:
        self.token_a, self.calls, self.status, self.down = token_a, [], 200, False

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.calls.append(request)
        if self.down:
            raise httpx2.ConnectError("rest tắt", request=request)
        if self.status != 200:
            return httpx2.Response(self.status, json={"code": "PGRST301", "message": "giả"})
        mine = request.headers.get("Authorization") == f"Bearer {self.token_a}"
        q = request.url.params
        if request.url.path == "/mau_in" and q.get("id") == "eq.1" and q.get("bang") == "eq.yeu_cau":
            return httpx2.Response(200, json=[{"noi_dung": TEMPLATE}] if mine else [])
        if request.url.path == "/yeu_cau" and q.get("id") == "eq.5":
            return httpx2.Response(200, json=[ROW] if mine else [])
        if request.url.path == "/yeu_cau":
            return httpx2.Response(200, json=[])
        return httpx2.Response(404, json={"code": "PGRST205", "message": "không có bảng"})


@pytest.fixture
def printing(settings, scanner, store, verifier, meili, vault, make_token, monkeypatch):
    pages: list[str] = []
    monkeypatch.setattr(sinh_print, "render_pdf", lambda page: pages.append(page) or b"%PDF-1.7 fake")
    token_a, token_b = make_token(tenant=str(TENANT_A)), make_token(tenant=str(TENANT_B))
    rest = FakeRest(token_a)
    app = create_app(settings, scanner=scanner, store=store, verifier=verifier, hasura=TenantHasura(), meili=meili,
                     vault=vault, rest=httpx2.AsyncClient(base_url="http://rest:3000",
                                                          transport=httpx2.MockTransport(rest)))
    with TestClient(app) as c:
        yield c, rest, pages, token_a, token_b


def get(c: TestClient, path: str, token: str | None) -> httpx2.Response:
    return c.get(path, headers={"Authorization": f"Bearer {token}"} if token else {})


def test_fill_escapes_values_and_template_text():
    row = {"a": "<script>alert(1)</script>", "b": "<img src=x onerror=alert(1)>"}
    page = sinh_print.fill("<b>{{a}}</b> {{b}}", row)
    assert "<script" not in page and "<img" not in page and "<b>" not in page
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page and "&lt;img src=x onerror=alert(1)&gt;" in page


def test_fill_layout_dates_and_single_pass():
    # cột không có thì rỗng; giá trị chứa {{…}} không bị thay lần nữa
    assert sinh_print.fill(TEMPLATE, {**ROW, "noi_dung": "{{tieu_de}}"}) == (
        '<div class="title">Phiếu yêu cầu</div><p>Tiêu đề: Máy in phòng 204<br>Hạn: 05/11/2026<br>Ghi chú: </p>'
        "<p>Nội dung: {{tieu_de}}</p>")
    assert sinh_print.fill("Lúc {{created_at}}", ROW) == "<p>Lúc 00:30 05/11/2026</p>"     # giờ Việt Nam
    assert sinh_print.fill("{{a}} {{b}} {{c}}", {"a": True, "b": 0, "c": None}) == "<p>Có 0 </p>"


def test_urls_in_template_stay_text():
    page = sinh_print.page_html(sinh_print.fill("file:///etc/passwd\nhttp://169.254.169.254/ {{x}}",
                                                {"x": "url(http://10.0.0.1/a)"}), {"name": "A"})
    assert "file:///etc/passwd<br>http://169.254.169.254/ url(http://10.0.0.1/a)" in page
    assert "src=" not in page and "href=" not in page and "@import" not in page


def weasyprint_or_skip():
    try:
        import weasyprint  # noqa: F401
    except OSError:
        pytest.skip("máy này thiếu thư viện Pango của WeasyPrint (image svc-files có sẵn)")


def test_fetcher_refuses_everything_but_data():
    weasyprint_or_skip()
    fetcher = sinh_print.only_data_urls()
    for url in ("file:///etc/passwd", "http://169.254.169.254/latest/meta-data/", "https://example.com/a.css"):
        with pytest.raises(ValueError, match="disallowed protocol"):
            fetcher.fetch(url)
    assert fetcher.fetch("data:text/plain,hi") is not None


def test_render_uses_the_data_only_fetcher(monkeypatch):
    weasyprint_or_skip()
    from weasyprint import URLFetcher

    asked: list[str] = []

    class Spy(URLFetcher):
        def fetch(self, url, *args, **kwargs):
            asked.append(url)
            return super().fetch(url, *args, **kwargs)

    monkeypatch.setattr(sinh_print, "only_data_urls", lambda: Spy(allowed_protocols=("data",)))
    page = sinh_print.page_html(sinh_print.fill("file:///etc/passwd http://169.254.169.254/", {}), {"name": "A"})
    assert sinh_print.render_pdf(page).startswith(b"%PDF-") and asked == []      # chữ thường: không tải gì
    # lớp chặn vẫn đứng khi trang có thẻ: WeasyPrint gọi bộ tải, bộ tải từ chối, PDF vẫn ra
    assert sinh_print.render_pdf('<img src="file:///etc/passwd">').startswith(b"%PDF-")
    assert asked == ["file:///etc/passwd"]


def test_prints_own_row_with_callers_token(printing):
    c, rest, pages, token_a, _ = printing
    res = get(c, "/api/sinh/yeu_cau/5/pdf?mau=1", token_a)
    assert res.status_code == 200 and res.content.startswith(b"%PDF")
    assert res.headers["content-type"] == "application/pdf"
    assert "yeu_cau-5.pdf" in res.headers["content-disposition"]
    assert res.headers["cache-control"] == "private, no-store"
    assert [(r.url.path, r.url.params.get("id")) for r in rest.calls] == [("/mau_in", "eq.1"), ("/yeu_cau", "eq.5")]
    for r in rest.calls:        # token của người gọi, không khóa quản trị
        assert r.headers["Authorization"] == f"Bearer {token_a}" and r.headers.get("X-Request-Id")
        assert not any(k.lower().startswith("x-hasura") for k in r.headers)
    assert "Trường CNTT &amp; TT" in pages[0] and "Máy in phòng 204" in pages[0] and "Hà Nội, ngày" in pages[0]


def test_row_or_template_of_other_unit_is_404(printing):
    c, _, pages, _, token_b = printing
    res = get(c, "/api/sinh/yeu_cau/5/pdf?mau=1", token_b)
    assert res.status_code == 404 and res.json()["detail"]["code"] == "not_found" and pages == []


def test_missing_row_table_or_template_is_404(printing):
    c, _, _, token_a, _ = printing
    for path in ("/api/sinh/yeu_cau/6/pdf?mau=1", "/api/sinh/yeu_cau/5/pdf?mau=2", "/api/sinh/khong_co/5/pdf?mau=1"):
        assert get(c, path, token_a).status_code == 404, path


@pytest.mark.parametrize("path", ["/api/sinh/Yeu_cau/5/pdf?mau=1", "/api/sinh/yeu-cau/5/pdf?mau=1",
                                  "/api/sinh/yeu_cau/0/pdf?mau=1", "/api/sinh/yeu_cau/5/pdf",
                                  "/api/sinh/yeu_cau/5/pdf?mau=1.5", "/api/sinh/yeu_cau/abc/pdf?mau=1",
                                  "/api/sinh/yeu_cau/1234567890123456789/pdf?mau=1"])
def test_bad_table_id_or_template_is_400(printing, path):
    c, rest, _, token_a, _ = printing
    res = get(c, path, token_a)
    assert res.status_code == 400 and res.json()["detail"]["code"] == "bad_request" and rest.calls == []


def test_token_and_upstream_errors(printing):
    c, rest, _, token_a, _ = printing
    assert get(c, "/api/sinh/yeu_cau/5/pdf?mau=1", None).status_code == 401 and rest.calls == []
    rest.status = 401
    assert get(c, "/api/sinh/yeu_cau/5/pdf?mau=1", token_a).status_code == 401
    rest.status = 500
    assert get(c, "/api/sinh/yeu_cau/5/pdf?mau=1", token_a).json()["detail"]["code"] == "rest_unavailable"
    rest.status, rest.down = 200, True
    res = get(c, "/api/sinh/yeu_cau/5/pdf?mau=1", token_a)
    assert res.status_code == 503 and res.json()["detail"]["code"] == "rest_unavailable"


def test_slow_render_is_503_busy(printing, monkeypatch):
    c, _, _, token_a, _ = printing
    monkeypatch.setattr(sinh_print, "PRINT_TIMEOUT_S", 0.05)
    monkeypatch.setattr(sinh_print, "render_pdf", lambda page: time.sleep(0.3) or b"%PDF")
    res = get(c, "/api/sinh/yeu_cau/5/pdf?mau=1", token_a)
    assert res.status_code == 503 and res.json()["detail"]["code"] == "busy" and res.headers["retry-after"] == "10"
