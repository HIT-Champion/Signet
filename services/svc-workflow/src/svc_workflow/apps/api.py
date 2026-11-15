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

"""API quy trình cho ứng dụng cắm bằng manifest (#301), qua APISIX ở ``/api/workflow/{app}/…``.

- ``GET  forms/{formKey}``: JSON Schema của form, đúng tệp manifest khai (bản đang triển khai);
- ``POST processes/{processKey}`` ``{"data": {…}}``: kiểm theo form của sự kiện bắt đầu → 201 ``{"id"}``. Biến hệ
  thống ``tenantId``, ``departmentId``, ``initiator`` lấy từ token; form không khai được tên đó
  (``additionalProperties: false``) nên client không ghi đè được;
- ``GET  processes``: đơn người này đã gửi; ``data``: dữ liệu form của đơn và của các bước đã xong (vd quyết định);
- ``GET  tasks``: việc của ứng dụng này mà người này được giao hoặc thuộc nhóm ứng viên, cùng thuê ước; ``data``: dữ
  liệu form đã ghi vào quy trình tới lúc đó; ``initiatorName``: tên người gửi đơn theo danh bạ ``core.users``, không
  tìm được thì ``null`` (#506) — không trả id người gửi;
- ``POST tasks/{taskId}`` ``{"data": {…}}``: kiểm theo form của việc, nhận rồi hoàn thành → 204;
- ``GET  processes/{processId}/files/{fileId}``: tệp đính kèm của đơn (#325), cho người gửi đơn và người có hoặc đã
  có việc trong đơn.

Trường tệp (``x-moc-file``, forms.py): trang của ứng dụng tải tệp lên ``POST /api/files`` của svc-files rồi gửi id
tệp trong ``data``. Lúc bắt đầu và lúc hoàn thành việc, tệp phải có trong thuê ước, do chính người gửi form tải lên,
không mã hóa, đúng loại và cỡ của trường; sai điều nào cũng chỉ ``{trường: "x-moc-file"}`` (không cho dò tệp của
người khác). Flowable chỉ giữ id. Danh sách đơn, việc thêm ``files``: trường → ``{id, filename, mimeType, sizeBytes}``.
Tải về: svc-workflow xét người xem, rồi lấy tệp qua đường nội bộ ``GET /internal/app-files/{id}`` của svc-files bằng
token dịch vụ. Một trường là tệp ở form này thì là tệp ở mọi form của gói (bundle.py): tệp chỉ đọc được qua trường
khai ``x-moc-file`` nên không ai gõ id tệp của người khác vào ô chữ rồi tải về được.

Lỗi kiểm: 422 ``{"errors": {trường: mã}}``, mã như ``schemas/README.md`` cộng ``x-moc-range`` (apps/forms.py). Lỗi
khác như svc-files: ``{"detail": {"code", "message"}}`` — 401 thiếu/sai token, 403 token không phải của client
``app-<tên>`` hoặc chưa gán đơn vị, 404 ứng dụng chưa cài hoặc đã gỡ, form/quy trình/việc không có hoặc không thuộc
ứng dụng, thuê ước, người này (không nói việc của người khác có tồn tại), 409 việc vừa có người khác nhận, 503 chưa
gọi được Flowable hoặc Keycloak.

``moc app remove`` tạm dừng mọi định nghĩa quy trình của ứng dụng (deploy.py) chứ không xóa deployment: lịch sử đơn
còn nguyên trong Flowable, còn API coi ứng dụng là đã gỡ (404) cho tới khi cài lại.

Form, mục lục đọc từ tài nguyên của đúng deployment (bundle.py), nhớ theo id deployment — nội dung một deployment
không bao giờ đổi. Việc của bản quy trình cũ kiểm theo form của chính bản đó.
"""

# Không dùng "from __future__ import annotations": FastAPI cần đọc được kiểu khai báo của các route trong install().
import json
import logging
import os
import uuid
from collections.abc import AsyncIterator, Coroutine, Mapping
from typing import Annotated, Any, Self

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from ..config import Settings
from ..flowable import FLOWABLE_ID, FlowableClient, FlowableError, Task
from ..hasura import Actor, HasuraClient, HasuraError
from ..notify import load_people
from ..service_token import FilesError, ServiceToken
from .auth import AppUser, AuthError, TokenVerifier
from .bpmn import NAME
from .bundle import INDEX, deployment_prefix, form_resource
from .files import AppFiles
from .forms import RESERVED, AppForm, file_bytes

log = logging.getLogger("svc_workflow")
CANCELLED = "huy-boi-nguoi-gui"   # deleteReason khi người gửi hủy đơn (#325); lịch sử Flowable giữ lý do
CACHE_LIMIT = 500           # mục lục, form, định nghĩa → deployment: bất biến, chỉ cần trần bộ nhớ
# Dữ liệu một form chỉ là vài trường đơn. Đọc quá thì dừng: không giữ cả thân (APISIX cho tới 64 MiB) trong bộ nhớ,
# không đưa chuỗi cỡ đó vào pattern của form (apps/forms.py)
MAX_BODY = 64 * 1024

DATA_BODY: dict[str, Any] = {"requestBody": {"required": True, "content": {"application/json": {"schema": {
    "type": "object", "required": ["data"],
    "properties": {"data": {"type": "object", "description": "Dữ liệu form: tên trường là tên biến của quy trình"}},
}}}}}
ERRORS_422 = {"description": "Dữ liệu chưa đúng form: {\"errors\": {trường: mã}} (schemas/README.md, x-moc-range)",
              "content": {"application/json": {"schema": {
                  "type": "object", "required": ["errors"],
                  "properties": {"errors": {"type": "object", "additionalProperties": {"type": "string"}}}}}}}
TOO_LARGE = {413: {"description": f"Thân yêu cầu lớn quá {MAX_BODY // 1024} KB"}}
# Tệp của thuê ước theo id: quyền service của Hasura lọc theo thuê ước (core_files.yaml)
FILES = """
query AppFiles($ids: [uuid!]!) {
  core_files(where: {id: {_in: $ids}}) { id filename mime_type size_bytes encrypted created_by }
}"""
COMMON = {401: {"description": "Thiếu hoặc sai token"},
          403: {"description": "Token không phải của client app-<tên>, hoặc tài khoản chưa gán đơn vị"},
          404: {"description": "Ứng dụng chưa cài hoặc đã gỡ"},
          503: {"description": "Chưa gọi được Flowable hoặc Keycloak, thử lại sau"}}


class FormInvalid(Exception):
    def __init__(self, errors: dict[str, str]) -> None:
        super().__init__(", ".join(sorted(errors)))
        self.errors = errors


async def invalid(request: Request, exc: FormInvalid) -> JSONResponse:
    return JSONResponse({"errors": exc.errors}, status_code=422)


def _fail(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, {"code": code, "message": message})


def unavailable(exc: FlowableError) -> HTTPException:
    log.warning(json.dumps({"event": "app.workflow.flowable_failed", "error": str(exc)[:300]}, ensure_ascii=False))
    return _fail(503, "workflow_unavailable", "Chưa gọi được động cơ quy trình, thử lại sau")


def rest_variables(values: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Biến ghi kiểu cho Flowable REST: chuỗi, số nguyên (long), số thực (double), đúng/sai giữ đúng kiểu."""
    out = []
    for name, value in values.items():
        if isinstance(value, bool):
            kind = "boolean"
        elif isinstance(value, int):
            kind = "long"
        elif isinstance(value, float):
            kind = "double"
        else:
            kind, value = "string", str(value)
        out.append({"name": name, "type": kind, "value": value})
    return out


def _variables(row: dict[str, Any]) -> dict[str, Any]:
    return {v["name"]: v.get("value") for v in row.get("variables") or []}


def _canonical_uuid(value: Any) -> bool:
    """Chuỗi uuid đúng dạng svc-files trả (chữ thường, có gạch): so được bằng ``==`` với biến Flowable."""
    try:
        return isinstance(value, str) and str(uuid.UUID(value)) == value
    except ValueError:
        return False


def _fits(row: dict[str, Any] | None, spec: dict[str, Any], user: AppUser) -> bool:
    """Tệp gắn được vào trường: có trong thuê ước, do chính người gửi form tải lên, không mã hóa, đúng loại và cỡ."""
    return (row is not None and row.get("created_by") == user.user_id and not row.get("encrypted")
            and row.get("mime_type") in spec["mime"] and int(row.get("size_bytes") or 0) <= file_bytes(spec))


def app_data(variables: Mapping[str, Any]) -> dict[str, Any]:
    """Biến của một phiên quy trình trừ biến hệ thống: chỉ trường các form của ứng dụng (form nào cũng
    ``additionalProperties: false``, AppForm.variables chỉ ghi trường đã khai) — đơn, rồi quyết định của các bước."""
    return {k: v for k, v in variables.items() if k not in RESERVED}


class AppWorkflow:
    """Phần "quy trình của ứng dụng" gắn vào svc-workflow theo khuôn ``parts.Part`` — luôn bật, không phụ thuộc
    ``MOC_OFFICE_ENABLED``."""

    def __init__(self, flowable: FlowableClient, verifier: TokenVerifier | None,
                 hasura: HasuraClient | None = None, files: AppFiles | None = None) -> None:
        self.flowable = flowable
        self.verifier = verifier
        self.hasura = hasura                    # danh bạ core.users (#506), core.files của tệp đính kèm (#325)
        self.files = files                      # svc-files: đọc tệp đính kèm cho người được xem
        self._index: dict[str, dict[str, Any] | None] = {}
        self._forms: dict[tuple[str, str], AppForm | None] = {}
        self._deployment_of: dict[str, str | None] = {}

    @classmethod
    def build(cls, settings: Settings, flowable: FlowableClient, *, verifier: TokenVerifier | None = None,
              hasura: HasuraClient | None = None, env: Mapping[str, str] = os.environ) -> Self:
        """issuer, JWKS như x-oidc của docker-compose.yml: iss là URL công khai của realm, khóa lấy qua mạng nội bộ.
        Đặt MOC_OIDC_ISSUER, MOC_OIDC_JWKS_URL để đổi; không có MOC_PUBLIC_URL thì API trả 503 (chưa cấu hình)."""
        issuer = env.get("MOC_OIDC_ISSUER") or (f"{settings.public_url}/realms/{settings.realm}"
                                                if settings.public_url else "")
        jwks = (env.get("MOC_OIDC_JWKS_URL")
                or f"{settings.keycloak_url}/realms/{settings.realm}/protocol/openid-connect/certs")
        # cùng tài khoản dịch vụ với Văn phòng (office/api.py), dựng riêng: phần này bật cả khi Văn phòng tắt
        files = AppFiles(settings.files_url, ServiceToken(
            settings.keycloak_url, settings.realm, settings.directory_client_id, settings.directory_client_secret))
        return cls(flowable, verifier or (TokenVerifier(issuer, jwks) if issuer else None), hasura, files)

    def jobs(self) -> list[Coroutine[Any, Any, None]]:
        return []                    # gói quy trình do moc app install triển khai, không có việc nền

    async def aclose(self) -> None:
        if self.files is not None:   # Flowable là máy khách chung, create_app đóng; svc-files là của riêng phần này
            await self.files.aclose()

    # --- đọc deployment ------------------------------------------------------------------------------------

    @staticmethod
    def _remember(cache: dict[Any, Any], key: Any, value: Any) -> Any:
        if len(cache) >= CACHE_LIMIT:
            cache.clear()
        cache[key] = value
        return value

    async def latest(self, app: str) -> str | None:
        """id deployment mới nhất của ứng dụng (bản moc app install vừa cài)."""
        prefix = deployment_prefix(app)
        rows = await self.flowable.deployments(f"{prefix}%", size=1)
        return next((r["id"] for r in rows if str(r.get("name", "")).startswith(prefix)), None)

    async def index(self, deployment_id: str) -> dict[str, Any] | None:
        if deployment_id not in self._index:
            raw = await self.flowable.resource(deployment_id, INDEX)
            self._remember(self._index, deployment_id, json.loads(raw) if raw else None)
        return self._index[deployment_id]

    async def form(self, deployment_id: str, form_key: str) -> AppForm | None:
        key = (deployment_id, form_key)
        if key not in self._forms:
            index = await self.index(deployment_id)
            raw = (await self.flowable.resource(deployment_id, form_resource(form_key))
                   if index and form_key in index.get("forms", []) else None)
            self._remember(self._forms, key, AppForm(json.loads(raw)) if raw else None)
        return self._forms[key]

    async def deployment_of(self, definition_id: str) -> str | None:
        if definition_id not in self._deployment_of:
            row = await self.flowable.definition(definition_id)
            self._remember(self._deployment_of, definition_id, row.get("deploymentId") if row else None)
        return self._deployment_of[definition_id]

    async def installed(self, app: str) -> tuple[str, list[dict[str, Any]]]:
        """Deployment mới nhất của ứng dụng và các định nghĩa đang chạy của nó. Chưa cài, hoặc đã gỡ (mọi định nghĩa
        tạm dừng) → 404, dù lịch sử đơn vẫn còn trong Flowable."""
        dep = await self.latest(app)
        rows = await self.flowable.definitions(deploymentId=dep) if dep else []
        live = [r for r in rows if r.get("deploymentId") == dep and not r.get("suspended")]
        if dep is None or not live:
            raise _fail(404, "app_not_installed", "Ứng dụng chưa cài hoặc đã gỡ")
        return dep, live

    # --- nghiệp vụ -----------------------------------------------------------------------------------------

    async def form_schema(self, app: str, form_key: str) -> dict[str, Any]:
        dep, _ = await self.installed(app)
        form = await self.form(dep, form_key) if form_key.startswith(f"{app}.") else None
        if form is None:
            raise _fail(404, "form_not_found", "Ứng dụng không có form này")
        return form.schema

    async def start(self, user: AppUser, app: str, key: str, data: Any) -> str:
        dep, live = await self.installed(app)
        index = await self.index(dep) if key.startswith(f"{app}.") else None
        start = ((index or {}).get("processes") or {}).get(key, {}).get("startForm")
        definition = next((r for r in live if r.get("key") == key), None) if start else None
        if definition is None:
            raise _fail(404, "process_not_found", "Ứng dụng không có quy trình này")
        form = await self.form(dep, start)
        if form is None:
            raise _fail(404, "form_not_found", "Không đọc được form bắt đầu của quy trình")
        errors = form.errors(data)
        if errors:
            raise FormInvalid(errors)
        await self.check_files(user, form, data)
        system = {"tenantId": str(user.tenant_id), "departmentId": str(user.department_id or ""),
                  "initiator": user.user_id}
        return await self.flowable.start_definition(definition["id"],
                                                    rest_variables({**form.variables(data), **system}))

    @staticmethod
    def _mine(user: AppUser, app: str, row: dict[str, Any]) -> bool:
        variables = _variables(row)
        return (variables.get("initiator") == user.user_id and variables.get("tenantId") == str(user.tenant_id)
                and str(row.get("processDefinitionId", "")).startswith(f"{app}."))

    async def my_processes(self, user: AppUser, app: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        dep, _ = await self.installed(app)
        index = await self.index(dep)
        rows: list[dict[str, Any]] = []
        # mỗi quy trình lấy offset + limit đơn mới nhất rồi gộp, cắt: đúng trang dù ứng dụng có nhiều quy trình
        for key in sorted(((index or {}).get("processes") or {})):
            rows += await self.flowable.historic_processes({
                "processDefinitionKey": key, "sort": "startTime", "order": "desc", "size": offset + limit,
                "variables": [
                    {"name": "initiator", "value": user.user_id, "operation": "equals", "type": "string"},
                    {"name": "tenantId", "value": str(user.tenant_id), "operation": "equals", "type": "string"},
                ]})
        page = sorted((row for row in rows if self._mine(user, app, row)), key=lambda r: r.get("startTime") or "",
                      reverse=True)[offset:offset + limit]
        out = [{
            "id": row["id"], "processKey": row["processDefinitionId"].split(":", 1)[0],
            "startedAt": row.get("startTime"), "endedAt": row.get("endTime"),
            # đơn xong bình thường không có deleteReason; có là bị hủy (người gửi, hay người vận hành trên Flowable)
            "cancelled": bool(row.get("deleteReason")), "data": app_data(_variables(row)),
        } for row in page]
        return await self.with_files(user, out, [row["processDefinitionId"] for row in page])

    async def cancel(self, user: AppUser, app: str, process_id: str) -> None:
        """Người gửi hủy đơn còn chờ duyệt. Đơn không có, của người khác, ứng dụng hay đơn vị khác đều 404 như nhau:
        không lộ đơn có tồn tại hay không."""
        await self.installed(app)
        rows = (await self.flowable.historic_processes({"processInstanceId": process_id})
                if FLOWABLE_ID.fullmatch(process_id) else [])
        row = next((r for r in rows if r.get("id") == process_id and self._mine(user, app, r)), None)
        if row is None:
            raise _fail(404, "process_not_found", "Đơn không còn hoặc không thuộc người này")
        finished = _fail(409, "already_finished", "Đơn đã xong, không hủy được")
        if row.get("endTime"):
            raise finished
        try:
            await self.flowable.delete_process(process_id, CANCELLED)
        except FlowableError as exc:
            if exc.status == 404:                   # vừa duyệt xong giữa lúc đọc và lúc hủy
                raise finished from exc
            raise

    async def tasks(self, user: AppUser, app: str) -> list[dict[str, Any]]:
        await self.installed(app)
        mine = {"processDefinitionKeyLike": f"{app}.%"}
        found: dict[str, Task] = {}
        queries = [{**mine, "assignee": user.user_id}]
        if user.groups:
            queries.append({**mine, "candidateGroupIn": user.groups, "unassigned": True})
        for query in queries:
            for task in await self.flowable.query_tasks(query):
                found[task.id] = task
        kept = [t for t in sorted(found.values(), key=lambda t: t.created_at)
                if t.process_key.startswith(f"{app}.") and t.variables.get("tenantId") == str(user.tenant_id)]
        # initiator là biến hệ thống (app_data bỏ đi) và chỉ là id: người duyệt cần tên người gửi, không cần id
        names = await self.names(user, {t.variables.get("initiator") for t in kept} - {None, ""})
        out = [{
            "id": task.id, "name": task.name, "formKey": task.form_key, "processKey": task.process_key,
            "processId": task.process_instance_id, "createdAt": task.created_at, "dueAt": task.due_at,
            "initiatorName": names.get(task.variables.get("initiator")), "data": app_data(task.variables),
        } for task in kept]
        return await self.with_files(user, out, [task.process_definition_id for task in kept])

    async def names(self, user: AppUser, ids: set[str]) -> dict[str, str]:
        """id → tên trong danh bạ ``core.users`` của thuê ước (đồng bộ từ Keycloak, directory.py), một lần hỏi cho
        cả danh sách như thông báo lấy tên người làm (notify.load_people). Người đã khóa, chưa đồng bộ thì không có
        tên; danh bạ lỗi thì cũng vậy — thiếu tên không làm hỏng danh sách việc."""
        if self.hasura is None or not ids:
            return {}
        try:
            people = await load_people(self.hasura, Actor(user.user_id, user.tenant_id, "service", None))
        except HasuraError as exc:
            log.warning(json.dumps({"event": "app.workflow.directory_failed", "error": str(exc)[:300]},
                                   ensure_ascii=False))
            return {}
        return {uid: people[uid].full_name for uid in ids if uid in people}

    async def _owned(self, user: AppUser, app: str, task_id: str) -> Task:
        task = await self.flowable.task(task_id)
        if (task is None or not task.process_key.startswith(f"{app}.")
                or task.variables.get("tenantId") != str(user.tenant_id)):
            raise _fail(404, "task_not_found", "Việc không còn hoặc không thuộc ứng dụng này")
        if task.assignee:
            mine = task.assignee == user.user_id
        else:
            mine = bool(set(await self.flowable.candidate_groups(task_id)) & set(user.groups))
        if not mine:
            raise _fail(404, "task_not_found", "Việc không còn hoặc không thuộc ứng dụng này")
        return task

    async def complete(self, user: AppUser, app: str, task_id: str, data: Any) -> None:
        await self.installed(app)
        task = await self._owned(user, app, task_id)
        dep = await self.deployment_of(task.process_definition_id)
        form = await self.form(dep, task.form_key) if dep else None
        if form is None:
            raise _fail(404, "form_not_found", "Không đọc được form của việc")
        errors = form.errors(data)
        if errors:
            raise FormInvalid(errors)
        await self.check_files(user, form, data)
        claimed = False
        if not task.assignee:
            try:
                await self.flowable.claim(task_id, user.user_id)
            except FlowableError as exc:
                if exc.status == 409:
                    raise _fail(409, "task_taken", "Việc này vừa có người khác nhận") from exc
                raise unavailable(exc) from exc
            claimed = True
        try:
            await self.flowable.complete_typed(task_id, rest_variables(form.variables(data)))
        except FlowableError as exc:
            if claimed:
                try:
                    await self.flowable.claim(task_id, None)
                except FlowableError:
                    log.warning(json.dumps({"event": "app.workflow.unclaim_failed", "task_id": task_id}))
            if exc.status == 404:
                raise _fail(404, "task_not_found", "Việc không còn — có thể đã có người xử lý") from exc
            raise unavailable(exc) from exc

    # --- tệp đính kèm (#325) --------------------------------------------------------------------------------

    async def file_rows(self, user: AppUser, ids: set[str]) -> dict[str, dict[str, Any]]:
        """id → dòng ``core.files`` cùng thuê ước, một lần hỏi cho cả tập. Không có Hasura, Hasura lỗi → HasuraError."""
        ids = {i for i in ids if _canonical_uuid(i)}
        if not ids:
            return {}
        if self.hasura is None:
            raise HasuraError("chưa cấu hình Hasura")
        data = await self.hasura.as_service(Actor(user.user_id, user.tenant_id, "service", None), FILES,
                                            {"ids": sorted(ids)})
        return {row["id"]: row for row in data.get("core_files") or []}

    async def check_files(self, user: AppUser, form: AppForm, data: dict[str, Any]) -> None:
        given = {name: data[name] for name in form.files if data.get(name) is not None}
        if not given:
            return
        try:
            rows = await self.file_rows(user, set(given.values()))
        except HasuraError as exc:
            log.warning(json.dumps({"event": "app.workflow.files_failed", "error": str(exc)[:300]}, ensure_ascii=False))
            raise _fail(503, "files_unavailable", "Chưa kiểm được tệp đính kèm, thử lại sau") from exc
        bad = {name: "x-moc-file" for name, fid in given.items() if not _fits(rows.get(fid), form.files[name], user)}
        if bad:
            raise FormInvalid(bad)

    async def file_fields(self, deployment_id: str | None) -> set[str]:
        """Trường tệp của các form trong một deployment (cùng kiểu ở mọi form, bundle.py)."""
        index = await self.index(deployment_id) if deployment_id else None
        names: set[str] = set()
        for form_key in (index or {}).get("forms", []):
            form = await self.form(deployment_id, form_key) if deployment_id else None
            names |= set(form.files) if form else set()
        return names

    async def with_files(self, user: AppUser, items: list[dict[str, Any]],
                         definitions: list[str]) -> list[dict[str, Any]]:
        """Thêm ``files`` (trường tệp → id, tên, loại, cỡ) vào từng đơn, việc; ``definitions``: định nghĩa quy trình
        của từng phần tử. Hasura lỗi thì ``files`` rỗng, danh sách vẫn trả, như tên người gửi."""
        wanted = []
        for item, definition in zip(items, definitions, strict=True):
            fields = await self.file_fields(await self.deployment_of(definition) if definition else None)
            wanted.append({f: item["data"][f] for f in sorted(fields) if _canonical_uuid(item["data"].get(f))})
        rows: dict[str, dict[str, Any]] = {}
        try:
            rows = await self.file_rows(user, {fid for w in wanted for fid in w.values()})
        except HasuraError as exc:
            log.warning(json.dumps({"event": "app.workflow.files_failed", "error": str(exc)[:300]}, ensure_ascii=False))
        for item, w in zip(items, wanted, strict=True):
            item["files"] = {f: {"id": fid, "filename": rows[fid]["filename"], "mimeType": rows[fid]["mime_type"],
                                 "sizeBytes": int(rows[fid]["size_bytes"])} for f, fid in w.items() if fid in rows}
        return items

    async def took_part(self, user: AppUser, process_id: str) -> bool:
        """Người đã làm hay đang được giao một việc của đơn, hoặc thuộc nhóm ứng viên của việc chưa ai nhận (luật của
        _owned). Việc xong luôn có người làm: complete() nhận việc trước khi hoàn thành."""
        if await self.flowable.historic_tasks({"processInstanceId": process_id, "taskAssignee": user.user_id,
                                               "size": 1}):
            return True
        return bool(user.groups) and bool(await self.flowable.query_tasks(
            {"processInstanceId": process_id, "candidateGroupIn": user.groups, "unassigned": True}))

    async def open_file(self, user: AppUser, app: str, process_id: str, file_id: str) -> Any:
        """Tệp đính kèm của một đơn (phản hồi svc-files đang mở) cho người gửi đơn và người có, đã có việc trong đơn.
        Đơn, tệp không có, tệp không nằm ở trường tệp của đơn hay người ngoài đều 404 như nhau."""
        await self.installed(app)
        hidden = _fail(404, "file_not_found", "Không có tệp này, hoặc bạn không được xem")
        rows = (await self.flowable.historic_processes({"processInstanceId": process_id})
                if FLOWABLE_ID.fullmatch(process_id) and _canonical_uuid(file_id) else [])
        row = next((r for r in rows if r.get("id") == process_id), None)
        variables = _variables(row) if row else {}
        if (row is None or variables.get("tenantId") != str(user.tenant_id)
                or not str(row.get("processDefinitionId", "")).startswith(f"{app}.")):
            raise hidden
        fields = await self.file_fields(await self.deployment_of(row["processDefinitionId"]))
        if file_id not in {variables.get(f) for f in fields}:
            raise hidden
        if variables.get("initiator") != user.user_id and not await self.took_part(user, process_id):
            raise hidden
        if self.files is None:
            raise _fail(503, "files_unavailable", "Chưa cấu hình svc-files")
        try:
            return await self.files.open(user.tenant_id, file_id)
        except FilesError as exc:
            if exc.status == 404:           # mã hóa, gắn văn bản hạn chế (svc-files không trả các tệp đó qua đây)
                raise hidden from exc
            log.warning(json.dumps({"event": "app.workflow.file_failed", "file_id": file_id, "error": str(exc)[:300]},
                                   ensure_ascii=False))
            raise _fail(503, "files_unavailable", "Chưa lấy được tệp, thử lại sau") from exc

    # --- route ---------------------------------------------------------------------------------------------

    def install(self, app: FastAPI) -> None:
        app.add_exception_handler(FormInvalid, invalid)  # type: ignore[arg-type]
        bearer = HTTPBearer(auto_error=False)
        verifier = self.verifier

        # Hàm thường (không async): FastAPI chạy trong threadpool, lần tải JWKS đầu không chặn event loop
        def caller(app: str, creds: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]) -> AppUser:
            if creds is None:
                raise HTTPException(401, {"code": "missing_token", "message": "Thiếu token đăng nhập"},
                                    {"WWW-Authenticate": "Bearer"})
            if verifier is None:
                raise _fail(503, "not_configured", "Chưa cấu hình kiểm token (MOC_PUBLIC_URL hoặc MOC_OIDC_ISSUER)")
            if not NAME.fullmatch(app):
                raise _fail(404, "app_not_found", "Không có ứng dụng này")
            try:
                return verifier.verify(creds.credentials, app)
            except AuthError as exc:
                headers = {"WWW-Authenticate": "Bearer"} if exc.status == 401 else None
                raise HTTPException(exc.status, {"code": exc.code, "message": exc.message}, headers) from exc

        User = Annotated[AppUser, Depends(caller)]

        async def body_data(request: Request) -> Any:
            too_large = _fail(413, "too_large", f"Thân yêu cầu lớn quá {MAX_BODY // 1024} KB")
            length = request.headers.get("content-length", "")
            if length.isdigit() and int(length) > MAX_BODY:
                raise too_large
            raw = bytearray()
            async for chunk in request.stream():         # không có Content-Length (chunked): đếm khi đọc
                raw += chunk
                if len(raw) > MAX_BODY:
                    raise too_large
            try:
                body = json.loads(raw)
            except (ValueError, RecursionError) as exc:     # RecursionError: mảng lồng hàng vạn tầng
                raise _fail(400, "bad_request", 'Thân yêu cầu phải là JSON {"data": {…}}') from exc
            if not isinstance(body, dict):
                raise _fail(400, "bad_request", 'Thân yêu cầu phải là JSON {"data": {…}}')
            return body.get("data", {})

        def rid(request: Request) -> str:
            return getattr(request.state, "request_id", "")

        tags = ["Quy trình của ứng dụng"]

        @app.get("/api/workflow/{app}/forms/{form_key}", tags=tags, responses={**COMMON, 404: {
                     "description": "Ứng dụng chưa cài, đã gỡ hoặc không có form này"}},
                 summary="JSON Schema của một form, đúng tệp manifest khai")
        async def get_form(app: str, form_key: str, user: User) -> dict[str, Any]:
            try:
                return await self.form_schema(app, form_key)
            except FlowableError as exc:
                raise unavailable(exc) from exc

        @app.post("/api/workflow/{app}/processes/{process_key}", status_code=201, tags=tags, openapi_extra=DATA_BODY,
                  responses={**COMMON, 404: {"description": "Ứng dụng chưa cài, đã gỡ hoặc không có quy trình này"},
                             422: ERRORS_422, **TOO_LARGE},
                  summary="Bắt đầu quy trình với dữ liệu form bắt đầu")
        async def start_process(app: str, process_key: str, user: User, request: Request) -> dict[str, str]:
            data = await body_data(request)
            try:
                pid = await self.start(user, app, process_key, data)
            except FormInvalid as exc:
                log.info(json.dumps({"event": "app.workflow.rejected", "app": app, "process_key": process_key,
                                     "fields": exc.errors, "user_id": user.user_id, "request_id": rid(request)}))
                raise
            except FlowableError as exc:
                raise unavailable(exc) from exc
            log.info(json.dumps({"event": "app.workflow.started", "app": app, "process_key": process_key,
                                 "process_id": pid, "user_id": user.user_id, "tenant_id": str(user.tenant_id),
                                 "request_id": rid(request)}))
            return {"id": pid}

        @app.get("/api/workflow/{app}/processes", tags=tags, responses=COMMON,
                 summary="Đơn người này đã gửi qua ứng dụng, mới nhất trước, từng trang")
        async def list_processes(app: str, user: User,
                                 limit: Annotated[int, Query(ge=1, le=100, description="Số đơn mỗi trang, 1–100; "
                                                             "trang đủ limit đơn thì có thể còn trang sau")] = 50,
                                 offset: Annotated[int, Query(ge=0, le=10000, description="Bỏ qua bao nhiêu đơn mới "
                                                              "nhất, 0–10000")] = 0) -> list[dict[str, Any]]:
            try:
                return await self.my_processes(user, app, limit, offset)
            except FlowableError as exc:
                raise unavailable(exc) from exc

        @app.delete("/api/workflow/{app}/processes/{process_id}", status_code=204, tags=tags,
                    responses={**COMMON,
                               404: {"description": "Ứng dụng đã gỡ; đơn không còn hoặc không thuộc người này"},
                               409: {"description": "Đơn đã duyệt xong hoặc đã hủy"}},
                    summary="Người gửi hủy đơn còn chờ duyệt")
        async def cancel_process(app: str, process_id: str, user: User, request: Request) -> Response:
            try:
                await self.cancel(user, app, process_id)
            except FlowableError as exc:
                raise unavailable(exc) from exc
            log.info(json.dumps({"event": "app.workflow.cancelled", "app": app, "process_id": process_id,
                                 "user_id": user.user_id, "tenant_id": str(user.tenant_id),
                                 "request_id": rid(request)}))
            return Response(status_code=204)

        @app.get("/api/workflow/{app}/processes/{process_id}/files/{file_id}", tags=tags,
                 response_class=StreamingResponse,
                 responses={**COMMON,
                            200: {"content": {"application/octet-stream": {}},
                                  "description": "Nội dung tệp, luôn ở dạng tải về"},
                            404: {"description": "Ứng dụng đã gỡ; đơn, tệp không có hoặc người này không được xem — "
                                               "trả như nhau"}},
                 summary="Tải tệp đính kèm của một đơn: người gửi đơn, người có hoặc đã có việc trong đơn")
        async def get_file(app: str, process_id: str, file_id: str, user: User, request: Request) -> StreamingResponse:
            try:
                r = await self.open_file(user, app, process_id, file_id)
            except FlowableError as exc:
                raise unavailable(exc) from exc
            log.info(json.dumps({"event": "app.workflow.file_read", "app": app, "process_id": process_id,
                                 "file_id": file_id, "user_id": user.user_id, "tenant_id": str(user.tenant_id),
                                 "request_id": rid(request)}))

            async def body() -> AsyncIterator[bytes]:
                try:                                    # cả khi người tải ngắt giữa chừng: trả kết nối tới svc-files
                    async for chunk in r.aiter_bytes():
                        yield chunk
                finally:
                    await r.aclose()

            kept = {k: r.headers[k] for k in ("content-length", "content-disposition", "etag") if k in r.headers}
            return StreamingResponse(body(), media_type=r.headers.get("content-type"),
                                     headers={**kept, "X-Content-Type-Options": "nosniff",
                                              "Cache-Control": "private, no-store"})

        @app.get("/api/workflow/{app}/tasks", tags=tags, responses=COMMON,
                 summary="Việc của ứng dụng giao cho người này hoặc nhóm của người này, cũ nhất trước")
        async def list_tasks(app: str, user: User) -> list[dict[str, Any]]:
            try:
                return await self.tasks(user, app)
            except FlowableError as exc:
                raise unavailable(exc) from exc

        @app.post("/api/workflow/{app}/tasks/{task_id}", status_code=204, tags=tags, openapi_extra=DATA_BODY,
                  responses={**COMMON,
                             404: {"description": "Ứng dụng đã gỡ; việc không còn hoặc không thuộc người này"},
                             409: {"description": "Việc vừa có người khác nhận"}, 422: ERRORS_422, **TOO_LARGE},
                  summary="Hoàn thành một việc với dữ liệu form của việc")
        async def complete_task(app: str, task_id: str, user: User, request: Request) -> Response:
            # Khai trả 204 nên chỉ có một return (204 không thân); lỗi ném ra cho FastAPI, invalid() ở trên
            data = await body_data(request)
            try:
                await self.complete(user, app, task_id, data)
            except FlowableError as exc:
                raise unavailable(exc) from exc
            log.info(json.dumps({"event": "app.workflow.task_completed", "app": app, "task_id": task_id,
                                 "user_id": user.user_id, "request_id": rid(request)}))
            return Response(status_code=204)
