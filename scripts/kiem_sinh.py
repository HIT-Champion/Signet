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

"""Kiểm /rest/v1 (PostgREST, #561) và khung của schema sinh (#562) trên hệ thống dựng thật (#567).

Bảng tạo bằng SQL qua API của Studio → postgres-meta (vai trò moc_studio), như người vận hành bấm trong Studio. Đọc,
ghi qua cổng APISIX (WAF bật như bản thật) bằng token Keycloak thật của hai đơn vị CNTT và KT. Ghi OpenAPI thật của
GET /rest/v1/ vào --out cho giao diện apps/sinh.

Cần make up, make seed và profile studio đang chạy. Thoát 0: đạt; 1: có ca sai hoặc không gọi được Signet.
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import uuid
from typing import Any, Callable

from moc_env import ENV, PUBLIC_URL, ROOT, HTTPError, call_json, compose, request, user_token, wait_for

PG_META = f"http://127.0.0.1:{ENV.get('MOC_STUDIO_PORT', '3400')}/api/platform/pg-meta/default"   # API của Studio
REST = f"{PUBLIC_URL}/rest/v1"
HASURA = "https://hasura.io/jwt/claims"
A, B, ADMIN = "vanthu", "vanthukt", "quantri"     # seed/users.csv: văn thư CNTT, văn thư KT, quản trị đơn vị CNTT
# Cú pháp lọc thường dùng của PostgREST mà bộ luật CRS 942xxx (dò SQL injection) của WAF có thể chặn nhầm
FILTERS = ["select=*", "select=id,tieu_de&order=id.desc&limit=5", "or=(tieu_de.eq.x,tieu_de.ilike.*in*)",
           "tieu_de=not.is.null", "id=in.(1,2,3)", "tieu_de=like.*a*", "created_at=gte.2026-01-01",
           "tieu_de=eq." + urllib.parse.quote("Máy in phòng 204"), "limit=1&offset=0"]


class Failed(Exception):
    pass


def ok(passed: bool, text: str) -> None:
    if not passed:
        raise Failed(text)
    print(f"   ✓ {text}")


def claims(token: str) -> dict[str, Any]:
    part = token.split(".")[1]
    return json.loads(base64.urlsafe_b64decode(part + "=" * (-len(part) % 4)))[HASURA]


def studio(query: str) -> list[dict[str, Any]]:
    return call_json("POST", f"{PG_META}/query", {"query": query})[0] or []


def refused(query: str) -> str:
    """Thân lỗi khi Studio bị từ chối lệnh; rỗng nếu lệnh chạy được."""
    try:
        studio(query)
    except HTTPError as exc:
        return exc.body
    return ""


def rest(method: str, path: str, token: str | None = None, body: Any = None) -> tuple[int, Any]:
    headers = {"Prefer": "return=representation"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    data = None if body is None else json.dumps(body).encode()
    try:
        status, _, raw = request(method, REST + path, data=data, headers=headers)
    except HTTPError as exc:
        return exc.status, exc.body
    return status, json.loads(raw) if raw else None


def until(check: Callable[[], bool], timeout_s: float = 15) -> bool:
    """PostgREST nạp lại schema khi nhận NOTIFY của khung, sau lệnh DDL một chút."""
    deadline = time.monotonic() + timeout_s
    while not check():
        if time.monotonic() > deadline:
            return False
        time.sleep(0.5)
    return True


def started_at() -> str:
    rest_id = compose("ps", "-q", "rest").decode().strip()
    return subprocess.run(["docker", "inspect", "-f", "{{.State.StartedAt}}", rest_id], check=True,
                          capture_output=True, text=True).stdout.strip()


def run(out: pathlib.Path) -> None:
    ok(ENV.get("MOC_WAF", "On") == "On", "WAF của APISIX bật (MOC_WAF=On), như bản thật")
    # image Studio, postgres-meta không có healthcheck: up --wait xong khi container chạy, chưa chắc đã trả lời
    wait_for(f"{PG_META}/tables?included_schemas=sinh", "Studio + postgres-meta", 180)
    ta, tb, tq = user_token(A), user_token(B), user_token(ADMIN)
    ca, cb = claims(ta), claims(tb)
    unit_a, unit_b = ca["x-hasura-tenant-id"], cb["x-hasura-tenant-id"]

    print("\n7. Không token, token sai chữ ký")
    ok(rest("GET", "/")[0] == 401, "không token: 401")
    ok(rest("GET", "/", ta[:-4] + ("AAAA" if ta[-4:] != "AAAA" else "BBBB"))[0] == 401, "token sửa chữ ký: 401")

    print("\nOpenAPI thật của GET /rest/v1/ (cho apps/sinh)")
    status, spec = rest("GET", "/", ta)
    ok(status == 200 and spec.get("swagger") == "2.0", f"token Keycloak thật: {status}, Swagger 2.0")
    out.mkdir(parents=True, exist_ok=True)
    (out / "openapi.json").write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    ok(spec["paths"].get("/yeu_cau", {}).get("get", {}).get("summary") == "Quản lý yêu cầu",
       "bảng mẫu sinh.yeu_cau của make seed có nhãn 'Quản lý yêu cầu'")

    t = f"kiem_{uuid.uuid4().hex[:6]}"
    q = f"sinh.{t}"
    print(f"\n1. Studio tạo bảng {q} qua postgres-meta")
    studio(f"create table {q} (id bigint generated by default as identity primary key, tieu_de text not null);"
           f" comment on table {q} is 'Kiểm e2e'; comment on column {q}.tieu_de is 'Tiêu đề'")
    row = studio(f"select (select string_agg(attname, ',' order by attname) from pg_attribute where attrelid = c.oid"
                 "         and attname in ('tenant_id', 'created_by', 'created_at') and not attisdropped) as cot,"
                 "  c.relrowsecurity as rls,"
                 "  (select string_agg(polname || ':' || polpermissive, ',' order by polname) from pg_policy"
                 "    where polrelid = c.oid) as policy,"
                 "  (select string_agg(tgname, ',' order by tgname) from pg_trigger"
                 "    where tgrelid = c.oid and not tgisinternal) as trig"
                 f" from pg_class c where c.oid = '{q}'::regclass")
    ok(row == [{"cot": "created_at,created_by,tenant_id", "rls": True, "policy": "moc_don_vi:false,moc_mo:true",
                "trig": "moc_cot_chuan,moc_khong_xoa_het,moc_so"}],
       "khung gắn ngay: cột chuẩn, RLS, policy đơn vị restrictive, trigger cột chuẩn/chặn TRUNCATE/sổ kiểm toán")
    ok(until(lambda: rest("GET", f"/{t}?limit=0", ta)[0] == 200), "/rest/v1 thấy bảng mới, không khởi động lại")

    print("\n2. Hai đơn vị, token thật: không thấy, không sửa được dòng của nhau")
    status, rows = rest("POST", f"/{t}", ta, {"tieu_de": "Máy in phòng 204", "tenant_id": unit_b, "created_by": "gia"})
    ok(status == 201 and rows[0]["tenant_id"] == unit_a and rows[0]["created_by"] == ca["x-hasura-user-id"],
       f"CNTT gửi tenant_id của KT, created_by giả: {status}, máy chủ ghi theo token của CNTT")
    a_id = rows[0]["id"]
    status, rows = rest("POST", f"/{t}", tb, {"tieu_de": "Xin cấp tài khoản"})
    ok(status == 201 and rows[0]["tenant_id"] == unit_b, f"KT thêm dòng của mình: {status}")
    for who, token, unit in (("CNTT", ta, unit_a), ("KT", tb, unit_b), ("quản trị đơn vị CNTT", tq, unit_a)):
        status, rows = rest("GET", f"/{t}?select=tenant_id", token)
        ok(status == 200 and rows == [{"tenant_id": unit}], f"{who} chỉ thấy dòng của đơn vị mình: {status}")
    for method, body in (("PATCH", {"tieu_de": "KT sửa"}), ("DELETE", None)):
        got = rest(method, f"/{t}?id=eq.{a_id}", tb, body)
        ok(got == (200, []), f"KT {method} dòng của CNTT: {got}, phải là 0 dòng")
    status, rows = rest("PATCH", f"/{t}?id=eq.{a_id}", ta, {"tenant_id": unit_b})
    ok(status == 200 and rows[0]["tenant_id"] == unit_a, f"CNTT chuyển dòng của mình sang KT: {status}, giữ nguyên")

    print("\nCú pháp lọc của PostgREST đi qua WAF")
    for f in FILTERS:
        status, _ = rest("GET", f"/{t}?{f}", ta)
        ok(status == 200, f"?{f}: {status}")

    print("\n3. Policy permissive 'true' thêm sau không mở được đơn vị khác")
    studio(f"create policy mo_het on {q} for select to clerk using (true)")
    status, rows = rest("GET", f"/{t}?select=tenant_id", ta)
    ok(status == 200 and rows == [{"tenant_id": unit_a}], f"CNTT vẫn chỉ thấy dòng của CNTT: {status}")
    studio(f"drop policy mo_het on {q}")

    print("\n4, 5. Khung hủy lệnh gỡ bảo vệ")
    for what, sql in (("view trong sinh", f"create view sinh.v_{t} as select * from {q}"),
                      ("hàm SECURITY DEFINER trong sinh", f"create function sinh.f_{t}() returns bigint language sql"
                                                          f" security definer as $$ select count(*) from {q} $$"),
                      ("DISABLE ROW LEVEL SECURITY", f"alter table {q} disable row level security")):
        ok("khung:" in refused(sql), f"{what}: bị hủy")
    ok(studio(f"select relrowsecurity as rls from pg_class where oid = '{q}'::regclass") == [{"rls": True}],
       "RLS vẫn bật")
    # Event trigger không bắt đổi tên schema; PostgreSQL đòi thêm quyền CREATE trên database, moc_studio không có
    body = refused("alter schema sinh rename to sinh_doi")
    if not body:
        studio("alter schema sinh_doi rename to sinh")
    ok("permission denied" in body, "đổi tên schema sinh (vòng ra ngoài khung): PostgreSQL từ chối")

    print("\n6. Studio thêm cột: /rest/v1 thấy ngay")
    t0 = started_at()
    studio(f"alter table {q} add column ghi_chu text; comment on column {q}.ghi_chu is 'Ghi chú'")
    ok(until(lambda: rest("POST", f"/{t}", ta, {"tieu_de": "Có ghi chú", "ghi_chu": "x"})[0] == 201),
       "thêm được dòng có cột mới")

    def labelled() -> bool:
        spec = rest("GET", "/", ta)[1]
        return spec["definitions"][t]["properties"].get("ghi_chu", {}).get("description") == "Ghi chú"
    ok(until(labelled), "OpenAPI có cột mới kèm nhãn 'Ghi chú'")
    ok(started_at() == t0, "PostgREST không khởi động lại")

    print("\nStudio xóa bảng: /rest/v1 bỏ bảng ngay")
    studio(f"drop table {q}")
    ok(until(lambda: t not in rest("GET", "/", ta)[1]["definitions"]), "OpenAPI không còn bảng đã xóa")

    print_templates(ta, tb)

    print("\n8. Sổ kiểm toán vẫn khớp")
    verify = subprocess.run([sys.executable, str(ROOT / "scripts" / "moc.py"), "audit", "verify"], check=False)
    ok(verify.returncode == 0, "moc audit verify: chuỗi băm khớp")


def print_templates(ta: str, tb: str) -> None:
    """#594: mẫu in văn bản thuần lưu được qua WAF; svc-files in dòng bằng token người gọi, dòng của đơn vị khác 404."""
    print("\nMẫu in: lưu qua /rest/v1, in PDF qua svc-files (#594)")
    body = {"ten": "Phiếu kiểm thử", "bang": "yeu_cau",
            "noi_dung": "# Phiếu yêu cầu\n\nTiêu đề: {{tieu_de}}\nHạn xử lý: {{han}}\n\nNội dung: {{ noi_dung }}"}
    status, rows = rest("POST", "/mau_in", ta, body)
    ok(status == 201, f"lưu mẫu có {{{{tieu_de}}}} qua WAF: {status}")
    mau = rows[0]["id"]
    status, rows = rest("POST", "/yeu_cau", ta, {"tieu_de": "In thử phiếu", "han": "2026-11-05"})
    ok(status == 201, f"CNTT thêm dòng để in: {status}")
    row = rows[0]["id"]

    def pdf(token: str, path: str) -> tuple[int, str, bytes]:
        try:
            status, headers, raw = request("GET", f"{PUBLIC_URL}/api/sinh/{path}",
                                           headers={"Authorization": f"Bearer {token}"})
        except HTTPError as exc:
            return exc.status, "", exc.body.encode()
        return status, {k.lower(): v for k, v in headers.items()}.get("content-type", ""), raw

    status, kind, raw = pdf(ta, f"yeu_cau/{row}/pdf?mau={mau}")
    ok(status == 200 and kind == "application/pdf" and raw.startswith(b"%PDF"),
       f"CNTT in dòng của mình: {status} {kind}")
    status, _, _ = pdf(tb, f"yeu_cau/{row}/pdf?mau={mau}")
    ok(status == 404, f"KT in dòng của CNTT: {status} (RLS, như dòng không có)")
    status, _, _ = pdf(ta, f"yeu_cau/{row}/pdf?mau=abc")
    ok(status == 400, f"mau không phải số: {status}")
    rest("DELETE", f"/yeu_cau?id=eq.{row}", ta)
    rest("DELETE", f"/mau_in?id=eq.{mau}", ta)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=pathlib.Path, default=ROOT / "out" / "sinh", help="nơi ghi openapi.json")
    args = parser.parse_args()
    try:
        run(args.out)
    except Failed as exc:
        print(f"\n✗ {exc}", file=sys.stderr)
        return 1
    except (HTTPError, urllib.error.URLError, OSError, KeyError, IndexError, TypeError, ValueError,
            subprocess.CalledProcessError) as exc:
        print(f"\n✗ Không chạy được: {exc}. Đã make up, make seed, bật profile studio chưa?", file=sys.stderr)
        return 1
    print("\nĐạt.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
