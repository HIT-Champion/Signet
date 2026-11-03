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

"""Chốt kỳ số liệu điều hành (#542, migration 1792281604300): lãnh đạo đơn vị chốt một tháng đã qua, bản chép không
sửa, không xóa được, mã băm vào sổ kiểm toán.

Đơn vị riêng cho test này, nên số biết trước và kỳ chốt không đụng các test khác.
"""

from __future__ import annotations

import json
import uuid

import pytest
from conftest import GraphQLError, SQLError, User, sql

CLOSE = """
mutation ($period: date!) {
  office_close_period(args: {period: $period}) { tenant_id period closed_at closed_by figures sha256 }
}"""
CLOSES = "{ office_period_closes { tenant_id period sha256 } }"
LAST_MONTH = "(date_trunc('month', now() at time zone 'Asia/Ho_Chi_Minh') - interval '1 month')::date"


@pytest.fixture(scope="module")
def director() -> User:
    tag = uuid.uuid4().hex[:6].upper()
    tenant = sql(f"insert into core.tenants (code, name) values ('K{tag}', 'Đơn vị thử chốt kỳ') returning id")[0][0]
    # một văn bản đến chưa vào sổ đã quá hạn: có số ở v_document_counts
    sql("insert into office.documents (tenant_id, direction, status, type_code, symbol, issuer_name, issued_on, summary, "
        f"due_on, created_by) values ('{tenant}', 'in', 'received', 'CV', '1/UBND-VP', 'UBND tỉnh', '2026-08-20', "
        f"'Văn bản đến thử chốt kỳ', '2026-09-01', 'van-thu-{tag}')")
    return User(f"lanh-dao-{tag}", "director", tenant)


@pytest.fixture(scope="module")
def last_month() -> str:
    return sql(f"select {LAST_MONTH}")[0][0]


def test_director_closes_a_past_month_once(director, last_month):
    row = director.gql(CLOSE, {"period": last_month})["office_close_period"][0]
    assert (row["tenant_id"], row["period"], row["closed_by"]) == (director.tenant, last_month, director.sub)
    figures = row["figures"]
    assert figures["period"] == last_month
    assert {"direction": "in", "restricted": False, "status": "received", "urgency": "normal", "overdue": True,
            "documents": 1} in figures["counts"]
    assert figures["processing"] is None and figures["outgoing"] is None   # tháng không có văn bản xong, đi

    # mã băm tính lại được từ chính bản chép; sổ kiểm toán ghi đúng mã đó, người chốt là lãnh đạo
    where = f"tenant_id = '{director.tenant}' and period = '{last_month}'"
    stored, again = sql("select encode(sha256, 'hex'), encode(sha256(convert_to(figures::text, 'UTF8')), 'hex') "
                        f"from office.period_closes where {where}")[0]
    assert stored == again
    actor, diff = sql("select actor_id, diff from core.audit_log where action = 'period.closed' "
                      f"and tenant_id = '{director.tenant}'")[0]
    assert actor == director.sub
    assert json.loads(diff) == {"period": last_month, "sha256": stored}

    with pytest.raises(GraphQLError, match="đã chốt"):
        director.gql(CLOSE, {"period": last_month})


def test_current_month_cannot_be_closed(director):
    today = sql("select (now() at time zone 'Asia/Ho_Chi_Minh')::date")[0][0]
    with pytest.raises(GraphQLError, match="chưa kết thúc"):
        director.gql(CLOSE, {"period": today})


def test_closed_period_is_frozen(director):
    # kỳ cũ ghi thẳng, không qua hàm: test này không phụ thuộc thứ tự chạy
    older = "(date_trunc('month', now()) - interval '2 months')::date"
    sql("insert into office.period_closes (tenant_id, period, closed_by, figures, sha256) values "
        f"('{director.tenant}', {older}, '{director.sub}', '{{}}', sha256('x'))")
    where = f"tenant_id = '{director.tenant}' and period = {older}"
    for statement in (f"update office.period_closes set figures = '{{}}' where {where}",
                      f"delete from office.period_closes where {where}",
                      "truncate office.period_closes"):
        with pytest.raises(SQLError, match="không sửa, không xóa"):
            sql(statement)


def test_only_directors_of_the_unit(world, director, last_month):
    for other in (world.clerk_a, world.manager_a1, world.staff_a1, world.admin_a):
        assert "errors" in other.raw(CLOSE, {"period": last_month}), other.role
        assert "errors" in other.raw(CLOSES), other.role
    # lãnh đạo đơn vị khác không thấy kỳ đã chốt của đơn vị này
    assert director.tenant not in {r["tenant_id"] for r in world.director_a.gql(CLOSES)["office_period_closes"]}
