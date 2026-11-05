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

"""Sơ đồ quy trình của văn bản (#603): DI của hai quy trình lõi, trạng thái từng bước, Action documentProcess."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from xml.etree import ElementTree

import pytest
from fastapi.testclient import TestClient

from conftest import DOC, OTHER, OUT, TENANT, actor
from svc_workflow.app import create_app
from svc_workflow.config import Settings
from svc_workflow.so_do import MODEL, layout, with_states
from svc_workflow.workflow import WorkflowError
from test_app import ENV, NoDirectory

ROOT = Path(__file__).resolve().parents[3]
PROCESSES = ROOT / "services" / "svc-workflow" / "processes"
CORE = ("van-ban-den", "van-ban-di")
SECRET = ENV["MOC_ACTION_SECRET"]


def run(coro):
    return asyncio.run(coro)


def process_of(key: str) -> ElementTree.Element:
    return ElementTree.parse(PROCESSES / f"{key}.bpmn20.xml").getroot().find(f"{MODEL}process")


def rows(key: str, done: tuple[str, ...] = (), active: tuple[str, ...] = ()) -> list[dict]:
    definition = f"{key}:3:abc"
    return ([{"activityId": a, "processDefinitionId": definition, "endTime": "2026-11-05T08:00:00Z"} for a in done]
            + [{"activityId": a, "processDefinitionId": definition, "endTime": None} for a in active])


# --- DI của hai quy trình lõi ------------------------------------------------------------------------

@pytest.mark.parametrize("key", CORE)
def test_every_element_of_a_core_process_is_drawn(key):
    process = process_of(key)
    flows = {el.get("id") for el in process if el.tag == f"{MODEL}sequenceFlow"}
    nodes = {el.get("id") for el in process if el.get("id")} - flows
    diagram = layout(PROCESSES / f"{key}.bpmn20.xml")
    assert diagram["key"] == key
    assert set(diagram["nodes"]) == nodes, "thêm phần tử vào quy trình thì thêm hình vào khối BPMNDiagram"
    assert set(diagram["edges"]) == flows
    assert all(len(e["points"]) >= 4 for e in diagram["edges"].values())


@pytest.mark.parametrize("key", CORE)
def test_shapes_do_not_overlap_and_edges_join_their_shapes(key):
    process = process_of(key)
    host = {el.get("id"): el.get("attachedToRef") for el in process if el.get("attachedToRef")}
    ends = {el.get("id"): (el.get("sourceRef"), el.get("targetRef"))
            for el in process if el.tag == f"{MODEL}sequenceFlow"}
    diagram = layout(PROCESSES / f"{key}.bpmn20.xml")
    nodes = list(diagram["nodes"].items())
    for i, (a, p) in enumerate(nodes):
        for b, q in nodes[i + 1:]:
            if host.get(a) == b or host.get(b) == a:  # boundary nằm trên mép việc chủ của nó
                continue
            apart = (p["x"] + p["w"] <= q["x"] or q["x"] + q["w"] <= p["x"]
                     or p["y"] + p["h"] <= q["y"] or q["y"] + q["h"] <= p["y"])
            assert apart, f"{a} chồng lên {b}"

    def on(x: float, y: float, n: dict) -> bool:
        return n["x"] - 1 <= x <= n["x"] + n["w"] + 1 and n["y"] - 1 <= y <= n["y"] + n["h"] + 1

    for flow, edge in diagram["edges"].items():
        source, target = (diagram["nodes"][e] for e in ends[flow])
        points = edge["points"]
        assert on(points[0], points[1], source) and on(points[-2], points[-1], target), flow


def test_states_follow_the_flowable_history():
    diagram = layout(PROCESSES / "van-ban-di.bpmn20.xml")
    # bị trả lại một lần rồi trình lại: lượt cũ của bước duyệt phòng đã xong, lượt mới đang chờ
    history = rows("van-ban-di", done=("trinh", "f1", "duyetPhong", "f2", "sauDuyetPhong", "f4", "chinhSua", "f8"),
                   active=("duyetPhong",)) + [{"activityId": "khongCo", "endTime": None}]
    for given in (history, history[::-1]):
        result = with_states(diagram, given)
        nodes = {n["id"]: n["state"] for n in result["nodes"]}
        edges = {e["id"]: e["state"] for e in result["edges"]}
        assert nodes["duyetPhong"] == "active" and nodes["chinhSua"] == "done" and nodes["duyetDonVi"] == ""
        assert edges["f4"] == "done" and edges["f3"] == ""
        assert "khongCo" not in nodes
    assert result["key"] == "van-ban-di" and result["width"] > 900 and result["height"] > 400
    assert next(n for n in result["nodes"] if n["id"] == "sauDuyetPhong")["kind"] == "exclusiveGateway"


# --- Workflow.document_process ---------------------------------------------------------------------

def test_reader_gets_the_diagram_of_the_document(workflow, hasura, flowable):
    hasura.document["process_id"] = "proc-1"
    flowable.activity_rows["proc-1"] = rows("van-ban-den", done=("vaoSo", "f1", "tachGoiY", "f1b", "chiDao"),
                                            active=("goiYGiaoViec", "phanCong"))
    result = run(workflow.document_process(actor("director"), DOC, str(PROCESSES)))
    nodes = {n["id"]: n["state"] for n in result["nodes"]}
    assert result["key"] == "van-ban-den"
    assert nodes["chiDao"] == "done" and nodes["phanCong"] == "active" and nodes["xuLy"] == ""


def test_document_out_of_reach_is_not_found(workflow, hasura, flowable):
    hasura.document["process_id"] = "proc-1"
    flowable.activity_rows["proc-1"] = rows("van-ban-den", active=("chiDao",))
    for who, doc in ((actor("director", tenant=OTHER), DOC), (actor("director"), "khong-phai-uuid"),
                     (actor("director"), "99999999-9999-4999-8999-999999999999")):
        with pytest.raises(WorkflowError) as err:
            run(workflow.document_process(who, doc, str(PROCESSES)))
        assert (err.value.status, err.value.code) == (404, "document_not_found"), doc
    # văn bản hạn chế: chỉ người có tên trong danh sách xem, như đọc văn bản
    hasura.document["restricted"] = True
    with pytest.raises(WorkflowError) as err:
        run(workflow.document_process(actor("staff", user="u-staff-dt"), DOC, str(PROCESSES)))
    assert err.value.code == "document_not_found"
    hasura.viewers.add("u-staff-dt")
    assert run(workflow.document_process(actor("staff", user="u-staff-dt"), DOC, str(PROCESSES)))["nodes"]


def test_document_without_a_process(workflow, hasura, flowable):
    with pytest.raises(WorkflowError) as err:  # dự thảo chưa trình: chưa có quy trình
        run(workflow.document_process(actor("staff"), OUT, str(PROCESSES)))
    assert (err.value.status, err.value.code) == (404, "no_process")
    hasura.outgoing["process_id"] = "proc-app"  # phiên không phải của Văn phòng thì không vẽ
    flowable.activity_rows["proc-app"] = rows("nghi-phep.don", active=("duyet",))
    with pytest.raises(WorkflowError) as err:
        run(workflow.document_process(actor("staff"), OUT, str(PROCESSES)))
    assert err.value.code == "no_process"
    flowable.down = True
    with pytest.raises(WorkflowError) as err:
        run(workflow.document_process(actor("staff"), OUT, str(PROCESSES)))
    assert (err.value.status, err.value.code) == (503, "workflow_unavailable")


# --- Action documentProcess ------------------------------------------------------------------------

@pytest.fixture
def client(hasura, flowable):
    settings = Settings.from_env({**ENV, "MOC_PROCESSES_DIR": str(PROCESSES)})
    app = create_app(settings, hasura=hasura, flowable=flowable, directory=NoDirectory())  # type: ignore[arg-type]
    with TestClient(app) as c:
        yield c


def action(c, role: str):
    return c.post("/actions/documentProcess", headers={"X-Moc-Action-Secret": SECRET}, json={
        "action": {"name": "documentProcess"}, "input": {"documentId": DOC},
        "session_variables": {"x-hasura-role": role, "x-hasura-user-id": "u-1", "x-hasura-tenant-id": str(TENANT)}})


def graphql_type(name: str) -> set[str]:
    sdl = (ROOT / "db" / "metadata" / "actions.graphql").read_text(encoding="utf-8")
    body = re.search(rf"^type {name} \{{(.*?)^\}}", sdl, re.S | re.M)
    assert body, name
    return set(re.findall(r"^\s+(\w+)\s*:", body.group(1), re.M))


def test_action_for_document_roles_with_the_graphql_shape(client, hasura, flowable):
    hasura.document["process_id"] = "proc-1"
    flowable.activity_rows["proc-1"] = rows("van-ban-den", done=("vaoSo",), active=("chiDao",))
    for role in ("clerk", "staff", "manager", "director"):
        r = action(client, role)
        assert r.status_code == 200, role
    result = r.json()
    assert set(result) == graphql_type("DocumentProcess")
    assert all(set(n) == graphql_type("ProcessNode") for n in result["nodes"])
    assert all(set(e) == graphql_type("ProcessEdge") for e in result["edges"])
    r = action(client, "tenant_admin")
    assert r.status_code == 403 and r.json()["extensions"]["code"] == "forbidden"
    hasura.document["process_id"] = None
    r = action(client, "clerk")
    assert r.status_code == 404 and r.json()["extensions"]["code"] == "no_process"


def test_hasura_metadata_declares_the_action():
    sdl = (ROOT / "db" / "metadata" / "actions.graphql").read_text(encoding="utf-8")
    assert "documentProcess(documentId: uuid!): DocumentProcess!" in sdl
    meta = (ROOT / "db" / "metadata" / "actions.yaml").read_text(encoding="utf-8")
    block = re.search(r"^  - name: documentProcess\n(.*?)(?=^  - name: |^custom_types:)", meta, re.S | re.M)
    assert block, "thiếu Action documentProcess trong db/metadata/actions.yaml"
    assert "type: query" in block.group(1) and "/actions/documentProcess'" in block.group(1)
    assert set(re.findall(r"- role: (\w+)", block.group(1))) == {"clerk", "staff", "manager", "director"}
    for name in ("DocumentProcess", "ProcessNode", "ProcessEdge"):
        assert f"    - name: {name}\n" in meta, name
