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

"""API quy trình cho ứng dụng ``/api/workflow/{app}/…`` (apps/api.py): token của đúng client app-<tên>, kiểm form,
biến hệ thống từ token, ai thấy việc nào, gỡ ứng dụng — với Flowable giả và token ký RSA thật."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import time
import uuid
from dataclasses import dataclass
from typing import Any

import httpx2
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app_fakes import APP, BPMN, DON, DUYET, AppFlowable, FakeAppFiles, FileStream, bundle_zip, form_bytes
from conftest import DEPT_DT, DEPT_KTPM, OTHER, TENANT, FakeHasura
from svc_workflow.apps import deploy
from svc_workflow.apps.api import CANCELLED, MAX_BODY, AppWorkflow, rest_variables
from svc_workflow.apps.auth import HASURA_CLAIMS, AppUser, AuthError, TokenVerifier, default_role
from svc_workflow.apps.bundle import BundleError, check_bundle
from svc_workflow.apps.files import AppFiles
from svc_workflow.config import Settings
from svc_workflow.hasura import HasuraError
from svc_workflow.service_token import FilesError, ServiceToken

ISSUER = "https://signet.example/realms/moc"
KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
API = f"/api/workflow/{APP}"
REQ = {"loai": "phep-nam", "tuNgay": "2026-11-02", "denNgay": "2026-11-04", "lyDo": "Về quê"}


@dataclass
class _Key:
    key: object


class StaticKeys:
    """Thay PyJWKClient: đúng một khóa công khai, không gọi mạng."""

    def __init__(self, key: object) -> None:
        self._key = _Key(key)

    def get_signing_key_from_jwt(self, token: str) -> _Key:
        return self._key


def token(sub: str = "u-staff", role: str = "staff", *, tenant: uuid.UUID | None = TENANT,
          dept: uuid.UUID | None = DEPT_DT, azp: str = f"app-{APP}", key: Any = KEY, ttl: int = 300,
          **extra: Any) -> str:
    now = int(time.time())
    ns: dict[str, Any] = {"x-hasura-user-id": sub, "x-hasura-allowed-roles": [role], "x-hasura-default-role": role}
    if tenant is not None:
        ns["x-hasura-tenant-id"] = str(tenant)
    if dept is not None:
        ns["x-hasura-department-id"] = str(dept)
    claims = {"iss": ISSUER, "sub": sub, "iat": now, "exp": now + ttl, "azp": azp, HASURA_CLAIMS: ns, **extra}
    return jwt.encode(claims, key, algorithm="RS256")


def auth(tok: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {tok}"}


STAFF = auth(token())
MANAGER = auth(token("u-manager", "manager"))
OTHER_MANAGER = auth(token("u-manager-ktpm", "manager", dept=DEPT_KTPM))
DIRECTOR = auth(token("u-director", "director", dept=None))
OTHER_TENANT = auth(token("u-staff-b", tenant=OTHER))


def install(fl: AppFlowable, **kwargs: Any) -> None:
    asyncio.run(deploy.install(fl, check_bundle(APP, bundle_zip(**kwargs))))


@pytest.fixture
def fl() -> AppFlowable:
    f = AppFlowable()
    install(f)
    return f


SENDER = "Nguyễn Văn An"


@pytest.fixture
def people() -> FakeHasura:
    """Danh bạ core.users của thuê ước: người gửi đơn ở các test là u-staff (token STAFF), thêm một người đã khóa."""
    return FakeHasura(users={
        "u-staff": {"id": "u-staff", "department_id": str(DEPT_DT), "role": "staff", "enabled": True,
                    "full_name": SENDER},
        "u-da-nghi": {"id": "u-da-nghi", "department_id": str(DEPT_DT), "role": "staff", "enabled": False,
                      "full_name": "Trần Văn Bình"},
    })


@pytest.fixture
def part(fl, people) -> AppWorkflow:
    return AppWorkflow(fl, TokenVerifier(ISSUER, "unused", keys=StaticKeys(KEY.public_key())), people)


@pytest.fixture
def client(part) -> TestClient:
    app = FastAPI()
    part.install(app)
    return TestClient(app)


def start(client: TestClient, data: dict[str, Any] | None = None, headers: dict[str, str] = STAFF) -> str:
    r = client.post(f"{API}/processes/{APP}.don", json={"data": data or REQ}, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["id"]


# --- token --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("headers, status, code", [
    ({}, 401, "missing_token"),
    (auth("khong-phai-jwt"), 401, "invalid_token"),
    (auth(token(ttl=-120)), 401, "invalid_token"),
    (auth(token(key=rsa.generate_private_key(public_exponent=65537, key_size=2048))), 401, "invalid_token"),
    (auth(token(iss="https://khac.example/realms/moc")), 401, "invalid_token"),
    (auth(token(azp="app-office")), 403, "wrong_client"),
    (auth(token(azp="moc-cli")), 403, "wrong_client"),
    (auth(token(azp="app-nghi-phep-khac")), 403, "wrong_client"),
    (auth(token(tenant=None)), 403, "no_tenant"),
])
def test_only_a_valid_token_of_the_apps_own_client_gets_in(client, headers, status, code):
    for method, path in (("GET", "/processes"), ("GET", "/tasks"), ("GET", f"/forms/{APP}.don"),
                         ("POST", f"/processes/{APP}.don"), ("POST", "/tasks/t-1"),
                         ("DELETE", f"/processes/{pending}")):
        r = client.request(method, API + path, headers=headers, json={"data": REQ})
        assert r.status_code == status and r.json()["detail"]["code"] == code, (method, path, r.text)
    if status == 401:
        assert r.headers["www-authenticate"] == "Bearer"


def test_token_of_one_app_does_not_open_another(client):
    r = client.get("/api/workflow/khac/processes", headers=STAFF)
    assert r.status_code == 403 and "app-khac" in r.json()["detail"]["message"]


def test_bad_app_name_is_404(client):
    assert client.get("/api/workflow/Nghi_Phep/tasks", headers=STAFF).status_code == 404


SECRETS = {"HASURA_ADMIN_SECRET": "x", "MOC_ACTION_SECRET": "x", "FLOWABLE_ADMIN_PASSWORD": "x",
           "MOC_DIRECTORY_CLIENT_SECRET": "x"}


def test_without_issuer_the_api_says_not_configured(fl):
    settings = Settings.from_env({**SECRETS, "MOC_PUBLIC_URL": ""})
    part = AppWorkflow.build(settings, fl, env={})
    assert part.verifier is None
    app = FastAPI()
    part.install(app)
    r = TestClient(app).get(f"{API}/tasks", headers=STAFF)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "not_configured"


def test_issuer_and_jwks_follow_the_compose_oidc_settings(fl):
    settings = Settings.from_env({**SECRETS, "MOC_PUBLIC_URL": "https://signet.example", "MOC_REALM": "moc"})
    part = AppWorkflow.build(settings, fl, env={})
    assert part.verifier is not None and part.verifier.issuer == "https://signet.example/realms/moc"
    part = AppWorkflow.build(settings, fl, env={"MOC_OIDC_ISSUER": "https://idp.example/realms/x"})
    assert part.verifier.issuer == "https://idp.example/realms/x"
    assert part.jobs() == [] and asyncio.run(part.aclose()) is None


def test_user_comes_from_hasura_claims():
    verifier = TokenVerifier(ISSUER, "unused", keys=StaticKeys(KEY.public_key()))
    user = verifier.verify(token("u-manager", "manager"), APP)
    assert user == AppUser("u-manager", TENANT, "manager", DEPT_DT, f"app-{APP}")
    assert user.groups == [f"t:{TENANT}:manager", f"t:{TENANT}:d:{DEPT_DT}:manager"]
    assert verifier.verify(token(dept=None, role="staff"), APP).groups == [f"t:{TENANT}:staff"]
    bad_dept = verifier.verify(token(dept=None, **{HASURA_CLAIMS: {
        "x-hasura-tenant-id": str(TENANT), "x-hasura-department-id": "khong-phai-uuid"}}), APP)
    assert bad_dept.department_id is None and bad_dept.role == "" and bad_dept.groups == []
    assert default_role("director", ("staff",)) == "" and default_role(None, ("staff",)) == "staff"


def test_unreachable_jwks_is_503():
    class Down:
        def get_signing_key_from_jwt(self, token: str) -> Any:
            raise jwt.PyJWKClientConnectionError("down")

    with pytest.raises(AuthError) as e:
        TokenVerifier(ISSUER, "unused", keys=Down()).verify(token(), APP)
    assert e.value.status == 503 and e.value.code == "jwks_unavailable"


# --- form ---------------------------------------------------------------------------------------------------


def test_form_is_the_schema_the_manifest_declared(client):
    r = client.get(f"{API}/forms/{APP}.don", headers=STAFF)
    assert r.status_code == 200 and r.json() == DON
    assert client.get(f"{API}/forms/{APP}.duyet", headers=STAFF).json() == DUYET


@pytest.mark.parametrize("form_key", [f"{APP}.khong-co", "van-ban-den.don", "vbden.chiDao"])
def test_unknown_or_foreign_form_is_404(client, form_key):
    r = client.get(f"{API}/forms/{form_key}", headers=STAFF)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "form_not_found"


def test_form_resources_are_read_once_per_deployment(client, fl):
    calls = []
    real = fl.resource

    async def counting(dep: str, name: str) -> bytes | None:
        calls.append(name)
        return await real(dep, name)

    fl.resource = counting
    for _ in range(3):
        client.get(f"{API}/forms/{APP}.don", headers=STAFF)
    assert calls == ["moc-app.json", f"{APP}.don.json"]


# --- bắt đầu quy trình -------------------------------------------------------------------------------------


def test_start_writes_typed_form_data_and_system_variables_from_the_token(client, fl):
    pid = start(client, {**REQ, "soNgay": 3, "khanCap": True})
    definition, variables = fl.started[0]
    assert definition == f"{APP}.don:1:dep-1" and pid.startswith("proc-")
    assert variables == [
        {"name": "loai", "type": "string", "value": "phep-nam"},
        {"name": "tuNgay", "type": "string", "value": "2026-11-02"},
        {"name": "denNgay", "type": "string", "value": "2026-11-04"},
        {"name": "soNgay", "type": "long", "value": 3},
        {"name": "khanCap", "type": "boolean", "value": True},
        {"name": "lyDo", "type": "string", "value": "Về quê"},
        {"name": "tenantId", "type": "string", "value": str(TENANT)},
        {"name": "departmentId", "type": "string", "value": str(DEPT_DT)},
        {"name": "initiator", "type": "string", "value": "u-staff"},
    ]


def test_user_without_department_starts_with_an_empty_department(client, fl):
    start(client, headers=DIRECTOR)
    assert {"name": "departmentId", "type": "string", "value": ""} in fl.started[0][1]


@pytest.mark.parametrize("data, errors", [
    ({**REQ, "tuNgay": "2026-11-04", "denNgay": "2026-11-02"}, {"denNgay": "x-moc-range"}),
    ({**REQ, "loai": "nghi-mat"}, {"loai": "enum"}),
    ({**REQ, "tenantId": str(OTHER)}, {"tenantId": "additionalProperties"}),
    ({**REQ, "initiator": "u-director"}, {"initiator": "additionalProperties"}),
    ({**REQ, "soNgay": 1.5, "khanCap": "co"}, {"soNgay": "type", "khanCap": "type"}),
    ({}, {"loai": "required", "tuNgay": "required", "denNgay": "required"}),
    ("khong-phai-doi-tuong", {"": "type"}),
])
def test_invalid_data_is_422_per_field_and_nothing_starts(client, fl, data, errors):
    r = client.post(f"{API}/processes/{APP}.don", json={"data": data}, headers=STAFF)
    assert r.status_code == 422 and r.json() == {"errors": errors}
    assert fl.started == []


def test_body_over_the_cap_is_413_and_nothing_starts(client, fl):
    big = {"data": {"loai": "phep-nam", "lyDo": "x" * MAX_BODY}}
    r = client.post(f"{API}/processes/{APP}.don", json=big, headers=STAFF)
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_large"
    assert fl.started == []


def test_body_without_content_length_is_counted_while_read(client, fl):
    # thân gửi từng khúc (chunked), không có Content-Length: vẫn dừng khi vượt trần
    chunks = (b"x" * 8192 for _ in range(MAX_BODY // 8192 + 2))
    r = client.post(f"{API}/tasks/{uuid.uuid4()}", content=chunks,
                    headers={**STAFF, "Content-Type": "application/json"})
    assert r.status_code == 413 and r.json()["detail"]["code"] == "too_large"


@pytest.mark.parametrize("body", [b"khong-phai-json", b"[1, 2]", b"[" * 50000])
def test_body_must_be_a_json_object(client, body):
    r = client.post(f"{API}/processes/{APP}.don", content=body, headers={**STAFF, "Content-Type": "application/json"})
    assert r.status_code == 400 and r.json()["detail"]["code"] == "bad_request"


@pytest.mark.parametrize("key", [f"{APP}.khong-co", "van-ban-den", f"{APP}.duyet"])
def test_unknown_or_foreign_process_is_404(client, fl, key):
    r = client.post(f"{API}/processes/{key}", json={"data": REQ}, headers=STAFF)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "process_not_found"
    assert fl.started == []


def test_flowable_down_is_503(client, fl):
    fl.down = True
    for r in (client.post(f"{API}/processes/{APP}.don", json={"data": REQ}, headers=STAFF),
              client.get(f"{API}/processes", headers=STAFF), client.get(f"{API}/tasks", headers=MANAGER),
              client.get(f"{API}/forms/{APP}.don", headers=STAFF),
              client.delete(f"{API}/processes/proc-1", headers=STAFF)):
        assert r.status_code == 503 and r.json()["detail"]["code"] == "workflow_unavailable"


def test_new_requests_use_the_latest_deployment(client, fl):
    install(fl, bpmn=BPMN.replace('flowable:dueDate="P2D"', 'flowable:dueDate="P3D"'))
    start(client)
    assert fl.started[0][0] == f"{APP}.don:2:dep-2"


# --- đơn của tôi, việc của tôi -----------------------------------------------------------------------------


def test_my_processes_hold_the_request_then_the_decision(client, fl):
    pid = start(client)
    start(client, headers=OTHER_TENANT)
    start(client, headers=MANAGER)
    r = client.get(f"{API}/processes", headers=STAFF)
    assert r.status_code == 200
    assert r.json() == [{"id": pid, "processKey": f"{APP}.don", "startedAt": fl.instances[pid]["startTime"],
                         "endedAt": None, "cancelled": False, "data": REQ, "files": {}}]
    fl.add_task("t-1", pid, groups=[f"t:{TENANT}:d:{DEPT_DT}:manager"])
    assert client.post(f"{API}/tasks/t-1", json={"data": {"quyetDinh": "dong-y", "ghiChu": "Được"}},
                       headers=MANAGER).status_code == 204
    fl.instances[pid]["endTime"] = "2026-10-26T11:00:00.000+07:00"
    mine = client.get(f"{API}/processes", headers=STAFF).json()
    assert mine[0]["endedAt"] == "2026-10-26T11:00:00.000+07:00"
    assert mine[0]["data"] == {**REQ, "quyetDinh": "dong-y", "ghiChu": "Được"}
    query = next(q for q in fl.queries if "processDefinitionKey" in q)
    assert query["processDefinitionKey"] == f"{APP}.don"
    assert {"name": "initiator", "value": "u-staff", "operation": "equals", "type": "string"} in query["variables"]


def test_tasks_show_the_request_to_the_managers_of_the_senders_department_only(client, fl):
    pid = start(client)
    fl.add_task("t-1", pid, groups=[f"t:{TENANT}:d:{DEPT_DT}:manager"], due="2026-10-28T09:30:00.000+07:00")
    r = client.get(f"{API}/tasks", headers=MANAGER)
    assert r.json() == [{"id": "t-1", "name": "Duyệt đơn nghỉ", "formKey": f"{APP}.duyet",
                         "processKey": f"{APP}.don", "processId": pid, "createdAt": "2026-10-26T09:30:00.000+07:00",
                         "dueAt": "2026-10-28T09:30:00.000+07:00", "initiatorName": SENDER, "data": REQ,
                         "files": {}}]
    assert "u-staff" not in r.text                       # tên người gửi, không phải id
    for who in (OTHER_MANAGER, STAFF, DIRECTOR, OTHER_TENANT):
        assert client.get(f"{API}/tasks", headers=who).json() == []
    assert all(q["processDefinitionKeyLike"] == f"{APP}.%" for q in fl.queries)


def test_task_names_the_sender_from_the_directory_in_one_lookup(client, fl, people):
    asked: list[tuple[str, uuid.UUID, str]] = []
    real = people.as_service

    async def counting(actor: Any, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        asked.append((query.split()[1], actor.tenant_id, actor.role))
        return await real(actor, query, variables)

    people.as_service = counting
    assert client.get(f"{API}/tasks", headers=MANAGER).json() == [] and asked == []   # không có việc: không hỏi
    pids = [start(client), start(client), start(client, headers=auth(token("u-chua-dong-bo"))),
            start(client, headers=auth(token("u-da-nghi")))]
    fl.instances["p-thieu"] = {"id": "p-thieu", "processDefinitionId": f"{APP}.don:1:dep-1", "endTime": None,
                               "startTime": "x", "variables": {"tenantId": str(TENANT)}}     # đơn không có initiator
    for n, pid in enumerate([*pids, "p-thieu"]):
        fl.add_task(f"t-{n}", pid, groups=[f"t:{TENANT}:d:{DEPT_DT}:manager"],
                    created=f"2026-10-26T09:3{n}:00.000+07:00")
    r = client.get(f"{API}/tasks", headers=MANAGER)
    assert [t["initiatorName"] for t in r.json()] == [SENDER, SENDER, None, None, None]
    assert asked == [("People", TENANT, "service")]      # một lần hỏi cho cả danh sách, đúng thuê ước
    for raw in ('"initiator"', "u-staff", "u-chua-dong-bo", "u-da-nghi"):
        assert raw not in r.text


def test_directory_down_leaves_the_name_empty_not_the_task_list(client, fl, people):
    async def down(actor: Any, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        raise HasuraError("Không gọi được Hasura")

    people.as_service = down
    fl.add_task("t-1", start(client), groups=[f"t:{TENANT}:d:{DEPT_DT}:manager"])
    r = client.get(f"{API}/tasks", headers=MANAGER)
    assert r.status_code == 200 and [(t["id"], t["initiatorName"]) for t in r.json()] == [("t-1", None)]


def test_assigned_task_is_seen_by_the_assignee(client, fl):
    pid = start(client)
    fl.add_task("t-xem", pid, assignee="u-staff")
    assert [t["id"] for t in client.get(f"{API}/tasks", headers=STAFF).json()] == ["t-xem"]
    assert client.get(f"{API}/tasks", headers=MANAGER).json() == []


def test_task_of_another_tenant_with_the_same_group_name_is_hidden(client, fl):
    pid = start(client, headers=OTHER_TENANT)
    fl.add_task("t-b", pid, groups=[f"t:{TENANT}:d:{DEPT_DT}:manager"])      # nhóm sai thuê ước: vẫn không lộ
    assert client.get(f"{API}/tasks", headers=MANAGER).json() == []
    r = client.post(f"{API}/tasks/t-b", json={"data": {"quyetDinh": "dong-y"}}, headers=MANAGER)
    assert r.status_code == 404


# --- hoàn thành việc ---------------------------------------------------------------------------------------


@pytest.fixture
def pending(client, fl) -> str:
    pid = start(client)
    fl.add_task("t-1", pid, groups=[f"t:{TENANT}:d:{DEPT_DT}:manager"])
    return pid


def test_complete_claims_then_completes_with_typed_variables(client, fl, pending):
    r = client.post(f"{API}/tasks/t-1", json={"data": {"quyetDinh": "tu-choi", "ghiChu": "Đủ người nghỉ"}},
                    headers=MANAGER)
    assert r.status_code == 204 and r.content == b""
    assert fl.claims == [("t-1", "u-manager")]
    assert fl.completed == [("t-1", [{"name": "quyetDinh", "type": "string", "value": "tu-choi"},
                                     {"name": "ghiChu", "type": "string", "value": "Đủ người nghỉ"}])]


@pytest.mark.parametrize("data, errors", [
    ({"quyetDinh": "Đồng ý"}, {"quyetDinh": "enum"}),
    ({"quyetDinh": "dong-y", "initiator": "u-manager"}, {"initiator": "additionalProperties"}),
    ({"quyetDinh": "dong-y", "ghiChu": None}, {"ghiChu": "type"}),
])
def test_invalid_decision_is_422_and_the_task_stays(client, fl, pending, data, errors):
    r = client.post(f"{API}/tasks/t-1", json={"data": data}, headers=MANAGER)
    assert r.status_code == 422 and r.json() == {"errors": errors}
    assert fl.claims == [] and fl.completed == []


@pytest.mark.parametrize("who", [OTHER_MANAGER, STAFF, DIRECTOR, OTHER_TENANT])
def test_people_outside_the_group_cannot_complete(client, fl, pending, who):
    r = client.post(f"{API}/tasks/t-1", json={"data": {"quyetDinh": "dong-y"}}, headers=who)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "task_not_found"
    assert fl.claims == [] and fl.completed == []


def test_task_taken_by_someone_else_is_409(client, fl, pending):
    fl.claim_conflict = True
    r = client.post(f"{API}/tasks/t-1", json={"data": {"quyetDinh": "dong-y"}}, headers=MANAGER)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "task_taken"


def test_failed_completion_gives_the_task_back(client, fl, pending):
    fl.gone_on_complete = True
    r = client.post(f"{API}/tasks/t-1", json={"data": {"quyetDinh": "dong-y"}}, headers=MANAGER)
    assert r.status_code == 404
    assert fl.claims == [("t-1", "u-manager"), ("t-1", None)]


def test_unknown_task_is_404(client):
    assert client.post(f"{API}/tasks/khong-co", json={"data": {"quyetDinh": "dong-y"}},
                       headers=MANAGER).status_code == 404


def test_office_task_is_not_reachable_through_the_app_api(client, fl):
    fl.instances["p-office"] = {"id": "p-office", "processDefinitionId": "van-ban-den:1:x", "endTime": None,
                                "startTime": "x", "variables": {"tenantId": str(TENANT)}}
    fl.add_task("t-office", "p-office", "vbden.chiDao", groups=[f"t:{TENANT}:d:{DEPT_DT}:manager"])
    assert client.get(f"{API}/tasks", headers=MANAGER).json() == []
    r = client.post(f"{API}/tasks/t-office", json={"data": {"quyetDinh": "dong-y"}}, headers=MANAGER)
    assert r.status_code == 404 and fl.claims == []


def test_task_of_an_older_version_is_checked_with_that_versions_form(client, fl, pending):
    stricter = copy.deepcopy(DUYET)
    stricter["properties"]["quyetDinh"]["enum"] = ["dong-y", "tu-choi", "can-bo-sung"]
    install(fl, duyet=stricter)
    assert client.get(f"{API}/forms/{APP}.duyet", headers=STAFF).json() == stricter
    r = client.post(f"{API}/tasks/t-1", json={"data": {"quyetDinh": "can-bo-sung"}}, headers=MANAGER)
    assert r.status_code == 422 and r.json() == {"errors": {"quyetDinh": "enum"}}


# --- phân trang, hủy đơn (#325) ----------------------------------------------------------------------------


def test_my_processes_come_in_pages_newest_first(client, fl):
    pids = [start(client) for _ in range(5)]
    start(client, headers=MANAGER)
    pages = [[p["id"] for p in client.get(f"{API}/processes", params={"limit": 2, "offset": offset},
                                          headers=STAFF).json()] for offset in (0, 2, 4, 6)]
    assert pages == [pids[:2:-1], pids[2:0:-1], pids[:1], []]
    assert [p["id"] for p in client.get(f"{API}/processes", headers=STAFF).json()] == pids[::-1]
    query = [q for q in fl.queries if "processDefinitionKey" in q][1]
    assert (query["sort"], query["order"], query["size"]) == ("startTime", "desc", 4)


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 101}, {"offset": -1}, {"offset": 10001},
                                    {"limit": "x"}])
def test_page_out_of_range_is_422(client, params):
    assert client.get(f"{API}/processes", params=params, headers=STAFF).status_code == 422


def test_sender_cancels_a_pending_request(client, fl, pending, caplog):
    with caplog.at_level(logging.INFO, logger="svc_workflow"):
        r = client.delete(f"{API}/processes/{pending}", headers={**STAFF, "X-Request-Id": "rid-huy-1"})
    assert r.status_code == 204 and r.content == b""
    assert fl.instances[pending]["deleteReason"] == CANCELLED
    assert client.get(f"{API}/tasks", headers=MANAGER).json() == []
    mine = client.get(f"{API}/processes", headers=STAFF).json()
    assert (mine[0]["cancelled"], mine[0]["endedAt"] is not None, mine[0]["data"]) == (True, True, REQ)
    events = [json.loads(m) for m in caplog.messages if "app.workflow.cancelled" in m]
    assert events == [{"event": "app.workflow.cancelled", "app": APP, "process_id": pending, "user_id": "u-staff",
                       "tenant_id": str(TENANT), "request_id": events[0]["request_id"]}]
    r = client.delete(f"{API}/processes/{pending}", headers=STAFF)       # hủy lần hai: đơn đã xong
    assert r.status_code == 409 and r.json()["detail"]["code"] == "already_finished"


@pytest.mark.parametrize("who", [MANAGER, OTHER_MANAGER, DIRECTOR, OTHER_TENANT])
def test_only_the_sender_can_cancel(client, fl, pending, who):
    r = client.delete(f"{API}/processes/{pending}", headers=who)
    assert r.status_code == 404 and r.json()["detail"] == {
        "code": "process_not_found", "message": "Đơn không còn hoặc không thuộc người này"}
    assert "deleteReason" not in fl.instances[pending]


@pytest.mark.parametrize("pid", ["khong-co", f"{APP}.don", "a:b", "x" * 65])
def test_unknown_process_is_404_like_someone_elses(client, fl, pid):
    r = client.delete(f"{API}/processes/{pid}", headers=STAFF)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "process_not_found"


def test_office_process_is_not_cancelled_through_the_app_api(client, fl):
    fl.instances["p-office"] = {"id": "p-office", "processDefinitionId": "van-ban-den:1:x", "endTime": None,
                                "startTime": "x", "variables": {"tenantId": str(TENANT), "initiator": "u-staff"}}
    assert client.delete(f"{API}/processes/p-office", headers=STAFF).status_code == 404
    assert "deleteReason" not in fl.instances["p-office"]


def test_finished_request_cannot_be_cancelled(client, fl, pending):
    fl.instances[pending]["endTime"] = "2026-10-26T11:00:00.000+07:00"
    r = client.delete(f"{API}/processes/{pending}", headers=STAFF)
    assert r.status_code == 409 and r.json()["detail"] == {
        "code": "already_finished", "message": "Đơn đã xong, không hủy được"}


def test_request_approved_while_cancelling_is_409(client, fl, pending):
    fl.finish_before_delete = True
    r = client.delete(f"{API}/processes/{pending}", headers=STAFF)
    assert r.status_code == 409 and r.json()["detail"]["code"] == "already_finished"
    assert "deleteReason" not in fl.instances[pending]


# --- gỡ, cài lại ---------------------------------------------------------------------------------------------


def test_removed_app_answers_404_but_history_stays_in_flowable(client, fl, pending):
    asyncio.run(deploy.remove(fl, APP))
    for method, path in (("GET", "/processes"), ("GET", "/tasks"), ("GET", f"/forms/{APP}.don"),
                         ("POST", f"/processes/{APP}.don"), ("POST", "/tasks/t-1")):
        r = client.request(method, API + path, headers=MANAGER, json={"data": {"quyetDinh": "dong-y"}})
        assert r.status_code == 404 and r.json()["detail"]["code"] == "app_not_installed", (method, path)
    assert pending in fl.instances and fl.completed == []
    install(fl)                                          # cài lại cùng bản: bật lại, đơn đang dở làm tiếp
    assert len(fl.deployed) == 1
    assert client.post(f"{API}/tasks/t-1", json={"data": {"quyetDinh": "dong-y"}}, headers=MANAGER).status_code == 204


def test_app_never_installed_is_404():
    app = FastAPI()
    AppWorkflow(AppFlowable(), TokenVerifier(ISSUER, "unused", keys=StaticKeys(KEY.public_key()))).install(app)
    r = TestClient(app).get(f"{API}/forms/{APP}.don", headers=STAFF)
    assert r.status_code == 404 and r.json()["detail"]["code"] == "app_not_installed"


def test_rest_variables_keep_types():
    assert rest_variables({"a": True, "b": 2, "c": 1.5, "d": "x"}) == [
        {"name": "a", "type": "boolean", "value": True}, {"name": "b", "type": "long", "value": 2},
        {"name": "c", "type": "double", "value": 1.5}, {"name": "d", "type": "string", "value": "x"}]


def test_openapi_lists_the_seven_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert sorted(paths) == [f"/api/workflow/{{app}}/{p}" for p in (
        "forms/{form_key}", "processes", "processes/{process_id}", "processes/{process_id}/files/{file_id}",
        "processes/{process_key}", "tasks", "tasks/{task_id}")]
    assert list(paths[f"{API.replace(APP, '{app}')}/processes/{{process_id}}"]) == ["delete"]
    assert form_bytes(DON)                               # mẫu dùng chung còn đọc được


# --- tệp đính kèm (#325) ------------------------------------------------------------------------------------------

PDF = {"mime": ["application/pdf"], "maxMB": 1}
DON_TEP = copy.deepcopy(DON)
DON_TEP["properties"]["giayTo"] = {"type": "string", "format": "uuid", "x-moc-file": PDF}
DUYET_TEP = copy.deepcopy(DUYET)
DUYET_TEP["properties"]["bienBan"] = {"type": "string", "format": "uuid", "x-moc-file": PDF}
TEP = "0b5e7a52-1c1d-4f0e-9a4a-3d2f1e0c9b01"            # của u-staff, PDF nhỏ
TEP_KHAC = "0b5e7a52-1c1d-4f0e-9a4a-3d2f1e0c9b02"       # mỗi tệp sai một điều
MANAGER_GROUP = f"t:{TENANT}:d:{DEPT_DT}:manager"


def file_row(by: str = "u-staff", *, tenant: uuid.UUID = TENANT, mime: str = "application/pdf",
             size: int = 2048, encrypted: bool = False, name: str = "giay-kham.pdf") -> dict[str, Any]:
    return {"tenant_id": str(tenant), "filename": name, "mime_type": mime, "size_bytes": size,
            "encrypted": encrypted, "created_by": by}


@pytest.fixture
def store() -> FakeAppFiles:
    files = FakeAppFiles()
    files.blobs[(str(TENANT), TEP)] = FileStream(b"%PDF-1.7 giay kham", "giay-kham.pdf", "application/pdf")
    return files


@pytest.fixture
def tep(people, store) -> TestClient:
    """Gói nghỉ phép có trường tệp ở form gửi (giayTo) và form duyệt (bienBan)."""
    fl = AppFlowable()
    install(fl, don=DON_TEP, duyet=DUYET_TEP)
    people.files[TEP] = {"id": TEP, **file_row()}
    app = FastAPI()
    AppWorkflow(fl, TokenVerifier(ISSUER, "unused", keys=StaticKeys(KEY.public_key())), people, store).install(app)
    client = TestClient(app)
    client.fl = fl                                       # type: ignore[attr-defined]
    return client


def test_start_keeps_only_the_file_id_and_lists_show_name_type_size(tep, store):
    pid = start(tep, {**REQ, "giayTo": TEP})
    assert {v["name"]: v["value"] for v in tep.fl.started[-1][1]}["giayTo"] == TEP
    info = {"giayTo": {"id": TEP, "filename": "giay-kham.pdf", "mimeType": "application/pdf", "sizeBytes": 2048}}
    assert tep.get(f"{API}/processes", headers=STAFF).json()[0]["files"] == info
    tep.fl.add_task("t-1", pid, groups=[MANAGER_GROUP])
    task = tep.get(f"{API}/tasks", headers=MANAGER).json()[0]
    assert task["data"]["giayTo"] == TEP and task["files"] == info
    assert store.calls == []                             # danh sách không đọc tệp


@pytest.mark.parametrize("row", [
    pytest.param(None, id="khong-co"),
    pytest.param(file_row("u-manager"), id="cua-nguoi-khac"),
    pytest.param(file_row(tenant=OTHER), id="don-vi-khac"),
    pytest.param(file_row(encrypted=True), id="ma-hoa"),
    pytest.param(file_row(mime="image/png"), id="sai-loai"),
    pytest.param(file_row(size=1024 * 1024 + 1), id="qua-co"),
])
def test_attachment_that_is_not_the_senders_own_fitting_file_is_one_422(tep, people, row):
    if row is not None:
        people.files[TEP_KHAC] = {"id": TEP_KHAC, **row}
    r = tep.post(f"{API}/processes/{APP}.don", json={"data": {**REQ, "giayTo": TEP_KHAC}}, headers=STAFF)
    assert r.status_code == 422 and r.json() == {"errors": {"giayTo": "x-moc-file"}}
    assert tep.fl.started == []


def test_attachment_is_checked_against_the_directory_or_nothing_starts(tep, people):
    async def down(actor: Any, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        raise HasuraError("Không gọi được Hasura")

    people.as_service = down
    r = tep.post(f"{API}/processes/{APP}.don", json={"data": {**REQ, "giayTo": TEP}}, headers=STAFF)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "files_unavailable"
    assert tep.fl.started == []
    pid = start(tep)                                     # đơn không kèm tệp không cần hỏi gì
    assert [(p["id"], p["files"]) for p in tep.get(f"{API}/processes", headers=STAFF).json()] == [(pid, {})]


def test_approver_attaches_only_a_file_of_their_own(tep, people):
    pid = start(tep, {**REQ, "giayTo": TEP})
    tep.fl.add_task("t-1", pid, groups=[MANAGER_GROUP])
    sent = tep.post(f"{API}/tasks/t-1", json={"data": {"quyetDinh": "dong-y", "bienBan": TEP}}, headers=MANAGER)
    assert sent.status_code == 422 and sent.json() == {"errors": {"bienBan": "x-moc-file"}}
    people.files[TEP_KHAC] = {"id": TEP_KHAC, **file_row("u-manager", name="bien-ban.pdf")}
    assert tep.post(f"{API}/tasks/t-1", json={"data": {"quyetDinh": "dong-y", "bienBan": TEP_KHAC}},
                    headers=MANAGER).status_code == 204
    assert set(tep.get(f"{API}/processes", headers=STAFF).json()[0]["files"]) == {"giayTo", "bienBan"}


def test_sender_and_the_approvers_download_the_file(tep, store):
    pid = start(tep, {**REQ, "giayTo": TEP})
    url = f"{API}/processes/{pid}/files/{TEP}"
    tep.fl.add_task("t-1", pid, groups=[MANAGER_GROUP, f"t:{TENANT}:director"])
    for who in (STAFF, MANAGER, DIRECTOR):               # người gửi; hai nhóm ứng viên của việc chưa ai nhận
        r = tep.get(url, headers=who)
        assert r.status_code == 200 and r.content == b"%PDF-1.7 giay kham"
        assert r.headers["content-disposition"].startswith("attachment;")
        assert r.headers["x-content-type-options"] == "nosniff" and "no-store" in r.headers["cache-control"]
    assert store.blobs[(str(TENANT), TEP)].closed
    for who in (OTHER_MANAGER, OTHER_TENANT, auth(token("u-staff-2"))):
        assert tep.get(url, headers=who).status_code == 404
    assert tep.post(f"{API}/tasks/t-1", json={"data": {"quyetDinh": "tu-choi"}}, headers=MANAGER).status_code == 204
    assert tep.get(url, headers=MANAGER).status_code == 200      # đã làm việc trong đơn: vẫn xem
    assert tep.get(url, headers=DIRECTOR).status_code == 404     # chỉ còn là ứng viên của việc người khác đã làm
    assert tep.get(url, headers=STAFF).status_code == 200        # đơn bị từ chối: tệp vẫn còn cho người gửi


def test_download_needs_the_file_in_a_file_field_of_that_request(tep, store, people):
    pid = start(tep, {**REQ, "giayTo": TEP})
    other = start(tep, {**REQ, "lyDo": TEP_KHAC})        # gõ id tệp vào ô chữ
    store.blobs[(str(TENANT), TEP_KHAC)] = FileStream(b"bi mat", "bi-mat.pdf", "application/pdf")
    for url in (f"{API}/processes/{other}/files/{TEP_KHAC}", f"{API}/processes/{other}/files/{TEP}",
                f"{API}/processes/{pid}/files/{TEP.upper()}", f"{API}/processes/{pid}/files/khong-phai-id",
                f"{API}/processes/khong-co/files/{TEP}"):
        r = tep.get(url, headers=STAFF)
        assert r.status_code == 404 and r.json()["detail"]["code"] == "file_not_found", url
    assert store.calls == []


def test_file_svc_files_refuses_is_404_and_svc_files_down_is_503(tep, store):
    pid = start(tep, {**REQ, "giayTo": TEP})
    url = f"{API}/processes/{pid}/files/{TEP}"
    store.refused.add(TEP)                               # vd đã gắn vào văn bản hạn chế
    assert tep.get(url, headers=STAFF).status_code == 404
    store.refused.clear()
    store.down = True
    r = tep.get(url, headers=STAFF)
    assert r.status_code == 503 and r.json()["detail"]["code"] == "files_unavailable"


def test_lists_leave_files_empty_when_the_directory_is_down(tep, people):
    pid = start(tep, {**REQ, "giayTo": TEP})

    async def down(actor: Any, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        raise HasuraError("Không gọi được Hasura")

    people.as_service = down
    mine = tep.get(f"{API}/processes", headers=STAFF).json()
    assert [(p["id"], p["data"]["giayTo"], p["files"]) for p in mine] == [(pid, TEP, {})]


def test_a_field_cannot_be_a_file_in_one_form_and_text_in_another():
    duyet = copy.deepcopy(DUYET)
    duyet["properties"]["giayTo"] = {"type": "string", "maxLength": 100}
    with pytest.raises(BundleError) as err:
        check_bundle(APP, bundle_zip(don=DON_TEP, duyet=duyet))
    assert any("giayTo là tệp (x-moc-file)" in e for e in err.value.errors)


def test_part_closes_its_own_svc_files_client(fl, people, store):
    asyncio.run(AppWorkflow(fl, None, people, store).aclose())
    assert store.closed


def test_app_files_reads_the_internal_route_with_a_fresh_token_after_401():
    seen: list[tuple[str, str, str]] = []
    tokens = iter(["tok-cu", "tok-moi", "tok-3"])

    def keycloak(request: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json={"access_token": next(tokens), "expires_in": 300})

    def svc_files(request: httpx2.Request) -> httpx2.Response:
        seen.append((request.url.path, request.url.params["tenant"], request.headers["authorization"]))
        if request.headers["authorization"] == "Bearer tok-cu":
            return httpx2.Response(401)
        if request.url.path.endswith(TEP_KHAC):
            return httpx2.Response(404)
        return httpx2.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})

    async def go() -> tuple[bytes, int | None]:
        token = ServiceToken("http://keycloak:8080", "moc", "svc-workflow", "s",
                             transport=httpx2.MockTransport(keycloak))
        client = AppFiles("http://svc-files:8000", token, transport=httpx2.MockTransport(svc_files))
        try:
            r = await client.open(TENANT, TEP)
            body = b"".join([chunk async for chunk in r.aiter_bytes()])
            await r.aclose()
            with pytest.raises(FilesError) as missing:
                await client.open(TENANT, TEP_KHAC)
            return body, missing.value.status
        finally:
            await client.aclose()

    assert asyncio.run(go()) == (b"%PDF", 404)
    assert seen == [(f"/internal/app-files/{TEP}", str(TENANT), "Bearer tok-cu"),
                    (f"/internal/app-files/{TEP}", str(TENANT), "Bearer tok-moi"),
                    (f"/internal/app-files/{TEP_KHAC}", str(TENANT), "Bearer tok-moi")]
