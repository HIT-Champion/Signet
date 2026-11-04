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

"""In một dòng của bảng sinh theo mẫu in (#586): GET /api/sinh/{bang}/{id}/pdf?mau={id}.

Mẫu là văn bản thuần ở bảng ``sinh.mau_in`` (migration 1792281604600_sinh_mau_in), không phải HTML: ``{{ten_cot}}``
là chỗ trống, dòng trống sang đoạn mới, dòng bắt đầu bằng ``# `` là tiêu đề. Lưu HTML qua /rest/v1 sẽ vướng luật XSS
của WAF; mẫu không có thẻ thì không có đường chạy script hay tải URL.

Mẫu và dòng lấy qua PostgREST (``rest:3000``) bằng chính token của người gọi: RLS của khung lọc theo đơn vị, nên dòng
hay mẫu của đơn vị khác ra 404 như dòng không có. Chỉ tên đơn vị ở đầu trang đọc bằng khóa quản trị Hasura, theo đơn
vị trong token đã kiểm. Mọi giá trị qua ``html.escape``; WeasyPrint chỉ được tải URL ``data:``.
"""

# Không dùng "from __future__ import annotations": FastAPI cần đọc được kiểu của dependency khai báo trong install().
import asyncio
import html
import re
from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated, Any
from zoneinfo import ZoneInfo

import httpx2
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import Response

from .auth import Principal
from .hasura import HasuraClient, HasuraError
from .web import DOWNLOAD_HEADERS, RETRY_AFTER, content_disposition

TABLE = re.compile(r"^[a-z_][a-z0-9_]*$")
NUMBER = re.compile(r"^[1-9][0-9]{0,17}$")      # bigint dương; số quá dài bị chặn trước khi gửi đi
SLOT = re.compile(r"\{\{\s*([a-z_][a-z0-9_]*)\s*\}\}")
DAY = re.compile(r"^(\d{4})-(\d{2})-(\d{2})$")
MOMENT = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}")
PRINT_TIMEOUT_S = 20.0
TENANT_QUERY = "query DonViIn($id: uuid!) { core_tenants_by_pk(id: $id) { name parent_name place_name } }"
VN = ZoneInfo("Asia/Ho_Chi_Minh")
# Khung đầu trang như văn bản của Văn phòng (render.py, NĐ 30 Phụ lục I), chép gọn: mô-đun ngoài Văn phòng không
# được import mô-đun của Văn phòng (scripts/ranh_gioi_loi.py)
CSS = """
@page { size: A4; margin: 20mm 15mm 20mm 30mm;
        @bottom-right { content: counter(page) "/" counter(pages); font-size: 10pt; color: #555; } }
html { font-family: "Liberation Serif", "Times New Roman", serif; font-size: 14pt; line-height: 1.3; color: #000; }
table.head { width: 100%; border-collapse: collapse; }
table.head td { vertical-align: top; text-align: center; padding: 0; }
td.org { width: 40%; font-size: 12pt; }
td.nation { width: 60%; font-size: 12pt; white-space: nowrap; }
.upper { text-transform: uppercase; }
.bold { font-weight: bold; }
.rule { width: 35%; margin: 1pt auto 6pt; border-top: 0.8pt solid #000; }
.rule.wide { width: 55%; }
.motto { font-size: 13pt; font-weight: bold; }
.place { font-style: italic; font-size: 13pt; margin-top: 6pt; }
.title { text-align: center; font-weight: bold; margin-top: 18pt; }
.body { margin-top: 10pt; text-align: justify; }
.body p { margin: 0 0 6pt; }
"""


def _error(status: int, code: str, message: str, headers: dict[str, str] | None = None) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message}, headers)


def _value(v: Any) -> str:
    """Giá trị cột thành chữ: ngày dd/mm/yyyy, thời điểm theo giờ Việt Nam, có/không; null là rỗng."""
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Có" if v else "Không"
    if isinstance(v, str) and (m := DAY.match(v)):
        return f"{m[3]}/{m[2]}/{m[1]}"
    if isinstance(v, str) and MOMENT.match(v):
        try:
            at = datetime.fromisoformat(v)
        except ValueError:
            return v
        return (at.astimezone(VN) if at.tzinfo else at).strftime("%H:%M %d/%m/%Y")
    return str(v)


def fill(template: str, row: dict[str, Any]) -> str:
    """Thân trang từ mẫu. Chữ của mẫu và giá trị cột đều thoát HTML; thay một lượt nên giá trị chứa ``{{…}}`` không
    bị thay tiếp. Chỗ trống không có cột thì để rỗng."""
    def line(text: str) -> str:
        return SLOT.sub(lambda m: html.escape(_value(row.get(m[1]))), html.escape(text))

    out: list[str] = []
    for block in re.split(r"\n[ \t]*\n", template.replace("\r\n", "\n")):
        lines: list[str] = []
        for raw in block.split("\n"):
            if raw.startswith("# "):
                if lines:
                    out.append(f"<p>{'<br>'.join(lines)}</p>")
                    lines = []
                out.append(f'<div class="title">{line(raw[2:].strip())}</div>')
            elif raw.strip():
                lines.append(line(raw.rstrip()))
        if lines:
            out.append(f"<p>{'<br>'.join(lines)}</p>")
    return "".join(out)


def vn_date(d: date, place: str | None) -> str:
    """'Hà Nội, ngày 05 tháng 02 năm 2026': ngày dưới 10 và tháng 1, 2 viết thêm số 0 (NĐ 30, Phụ lục I)."""
    month = f"{d.month:02d}" if d.month <= 2 else str(d.month)
    return f"{html.escape(place) + ', ' if place else ''}ngày {d.day:02d} tháng {month} năm {d.year}"


def page_html(body: str, tenant: dict[str, Any]) -> str:
    """Khung A4 cố định như đầu văn bản (NĐ 30, Phụ lục I): đơn vị, quốc hiệu, tiêu ngữ, ngày in."""
    parent, name = tenant.get("parent_name"), html.escape(tenant.get("name") or "")
    return f"""<!doctype html>
<html lang="vi"><head><meta charset="utf-8"><title>{name}</title>
<style>{CSS}</style></head>
<body><table class="head"><tr>
  <td class="org">
    {f'<div class="upper">{html.escape(parent)}</div>' if parent else ''}
    <div class="upper bold">{name}</div>
    <div class="rule"></div>
  </td>
  <td class="nation">
    <div class="upper bold">Cộng hòa xã hội chủ nghĩa Việt Nam</div>
    <div class="motto">Độc lập - Tự do - Hạnh phúc</div>
    <div class="rule wide"></div>
    <div class="place">{vn_date(datetime.now(VN).date(), tenant.get("place_name"))}</div>
  </td>
</tr></table>
<div class="body">{body}</div>
</body></html>"""


def only_data_urls() -> Any:
    """Bộ tải URL của WeasyPrint chỉ nhận ``data:``: bộ mặc định đọc được ``file:`` và gọi được ``http:``, nên một
    đường dẫn lọt vào trang sẽ đọc tệp của máy chủ hay gọi vào mạng nội bộ. Giữ lớp này cả khi mẫu không có thẻ."""
    from weasyprint import URLFetcher

    return URLFetcher(allowed_protocols=("data",), allow_redirects=False, timeout=1)


def render_pdf(page: str) -> bytes:
    from weasyprint import HTML       # nạp khi cần: test của phần khác không phải có Pango

    return HTML(string=page, url_fetcher=only_data_urls()).write_pdf()


async def _rest_one(rest: httpx2.AsyncClient, path: str, params: dict[str, str], headers: dict[str, str],
                    missing: str) -> dict[str, Any]:
    """Một dòng qua PostgREST bằng token người gọi. Không thấy (RLS, không có, bảng hay cột không có) đều là 404."""
    try:
        res = await rest.get(path, params=params, headers=headers)
    except httpx2.HTTPError as exc:
        raise _error(503, "rest_unavailable", "Dịch vụ dữ liệu chưa sẵn sàng, thử lại sau") from exc
    if res.status_code == 401:
        raise _error(401, "invalid_token", "Token không hợp lệ với dịch vụ dữ liệu", {"WWW-Authenticate": "Bearer"})
    if res.status_code in (400, 403, 404, 406):
        raise _error(404, "not_found", missing)
    if res.status_code != 200:
        raise _error(503, "rest_unavailable", "Dịch vụ dữ liệu chưa sẵn sàng, thử lại sau")
    rows = res.json()
    if not isinstance(rows, list) or not rows or not isinstance(rows[0], dict):
        raise _error(404, "not_found", missing)
    return rows[0]


def install(app: FastAPI, *, rest: httpx2.AsyncClient, hasura: HasuraClient, principal: Callable[..., Principal],
            ) -> None:
    """Gắn đường in. ``rest``: máy khách tới PostgREST (``MOC_REST_URL``, mặc định ``http://rest:3000``)."""
    printing = asyncio.Semaphore(2)     # WeasyPrint tốn CPU: không để lần in chiếm hết luồng của tải tệp

    def busy(message: str) -> HTTPException:
        return _error(503, "busy", message, {"Retry-After": RETRY_AFTER})

    async def build(page: str) -> bytes:
        try:
            await asyncio.wait_for(printing.acquire(), PRINT_TIMEOUT_S)
        except TimeoutError:
            raise busy("Đang in nhiều, thử lại sau ít giây") from None
        job = asyncio.ensure_future(asyncio.to_thread(render_pdf, page))
        job.add_done_callback(lambda _: printing.release())    # nhả khi luồng dựng xong thật, kể cả sau khi trả 503
        try:
            return await asyncio.wait_for(asyncio.shield(job), PRINT_TIMEOUT_S)
        except TimeoutError:
            raise busy("Dựng PDF quá lâu, thử lại sau ít giây") from None

    @app.get(
        "/api/sinh/{bang}/{row_id}/pdf",
        response_class=Response,
        summary="In một dòng của bảng sinh theo mẫu in (#586)",
        description="Mẫu (`sinh.mau_in`) và dòng lấy qua /rest/v1 bằng token của người gọi: RLS lọc theo đơn vị. "
                    "Mẫu là văn bản thuần: `{{ten_cot}}`, dòng trống sang đoạn mới, dòng `# ` là tiêu đề.",
        responses={
            200: {"content": {"application/pdf": {}}, "description": "Trang A4: đơn vị, quốc hiệu, ngày, thân mẫu"},
            400: {"description": "Tên bảng, id hay mau sai dạng"},
            401: {"description": "Thiếu hoặc sai token"},
            404: {"description": "Không có dòng hay mẫu, mẫu của bảng khác, hoặc của đơn vị khác: trả như nhau"},
            503: {"description": "Dịch vụ dữ liệu, CSDL chưa sẵn sàng; `busy` (kèm `Retry-After`) khi in quá giờ"},
        },
    )
    async def print_row(bang: str, row_id: str, request: Request,
                        who: Annotated[Principal, Depends(principal)], mau: str = "") -> Response:
        if not TABLE.match(bang) or not NUMBER.match(row_id) or not NUMBER.match(mau):
            raise _error(400, "bad_request", "Tên bảng là chữ thường, số, gạch dưới; id và mau là số nguyên dương")
        headers = {"Authorization": f"Bearer {who.token}", "X-Request-Id": request.state.request_id}
        template = await _rest_one(rest, "/mau_in", {"select": "noi_dung", "id": f"eq.{mau}", "bang": f"eq.{bang}"},
                                   headers, "Không có mẫu in này cho bảng, hoặc mẫu không thuộc đơn vị của bạn")
        row = await _rest_one(rest, f"/{bang}", {"id": f"eq.{row_id}"}, headers,
                              "Không có dòng này, hoặc dòng không thuộc đơn vị của bạn")
        try:
            data = await hasura.admin(TENANT_QUERY, {"id": str(who.tenant_id)})
        except HasuraError as exc:
            raise _error(503, "database_unavailable", "CSDL chưa sẵn sàng, thử lại sau") from exc
        page = page_html(fill(str(template.get("noi_dung") or ""), row), data.get("core_tenants_by_pk") or {})
        pdf = await build(page)
        return Response(pdf, media_type="application/pdf", headers={
            **DOWNLOAD_HEADERS, "Content-Disposition": content_disposition(f"{bang}-{row_id}.pdf"),
        })
