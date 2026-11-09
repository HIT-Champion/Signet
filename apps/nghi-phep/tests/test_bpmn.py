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

"""Quy trình của Đơn nghỉ phép (workflow/don-nghi-phep.bpmn20.xml) đọc bằng xml.etree, không cần Flowable: chỉ phần tử
lõi nhận cho ứng dụng cài thêm, không mã chạy trên máy chủ; nhóm duyệt đúng dạng nhóm trưởng phòng mà quy trình văn
bản đi của lõi dùng (cùng tên biến), bước Hiệu trưởng là nhóm director của đơn vị; mọi nút đi được từ lúc gửi đơn tới
một kết thúc; mỗi cổng rẽ phủ đúng các quyết định của form duyệt, cổng của trưởng phòng chia đôi theo số ngày làm việc;
timer quá hạn chuyển đơn lên Hiệu trưởng; sơ đồ vẽ đủ mọi nút. Lõi vẫn tự kiểm lúc cài — test này giữ tệp của ứng
dụng không trượt khỏi danh sách đó. Chạy: python3 -m unittest discover -s apps/nghi-phep/tests (make test)."""

from __future__ import annotations

import json
import pathlib
import re
import unittest
import xml.etree.ElementTree as ET

APP = pathlib.Path(__file__).resolve().parent.parent
ROOT = APP.parent.parent
BPMN = APP / "workflow" / "don-nghi-phep.bpmn20.xml"
OFFICE = ROOT / "services" / "svc-workflow" / "processes" / "van-ban-di.bpmn20.xml"
NS = {"b": "http://www.omg.org/spec/BPMN/20100524/MODEL", "di": "http://www.omg.org/spec/BPMN/20100524/DI"}
MODEL = "{" + NS["b"] + "}"
FLOWABLE = "{http://flowable.org/bpmn}"
# Phần tử ứng dụng được dùng trong <process> (danh sách trắng của #301): không scriptTask, serviceTask, listener…
ALLOWED = {"startEvent", "userTask", "exclusiveGateway", "endEvent", "sequenceFlow", "conditionExpression",
           "boundaryEvent", "timerEventDefinition", "timeDuration"}
# Thuộc tính flowable: được dùng; class, expression, delegateExpression… gọi mã trên máy chủ
FLOWABLE_ATTRS = {"formKey", "initiator", "candidateGroups"}
CONDITION = re.compile(r"\$\{quyetDinh == '([a-z0-9-]+)'(?: && soNgayLam (<=|>) 3)?\}")
GROUP = "t:${tenantId}:d:${departmentId}:manager"
PRINCIPAL = "t:${tenantId}:director"


def tag(el: ET.Element) -> str:
    return el.tag.split("}", 1)[1]


class Bpmn(unittest.TestCase):
    def setUp(self) -> None:
        self.root = ET.parse(BPMN).getroot()
        processes = self.root.findall("b:process", NS)
        self.assertEqual(len(processes), 1)
        self.process = processes[0]

    def test_only_whitelisted_elements_and_attributes(self) -> None:
        for el in self.process.iter():
            if el is self.process:
                continue
            with self.subTest(element=el.tag):
                self.assertTrue(el.tag.startswith(MODEL), "phần tử ngoài BPMN chuẩn (extensionElements…)")
                self.assertIn(tag(el), ALLOWED)
                extra = {k[len(FLOWABLE):] for k in el.attrib if k.startswith(FLOWABLE)} - FLOWABLE_ATTRS
                self.assertEqual(extra, set())
        text = BPMN.read_text(encoding="utf-8")
        for word in ("scriptTask", "serviceTask", "Listener", "flowable:class", "flowable:expression",
                     "delegateExpression", "script>"):
            self.assertNotIn(word, text)

    def test_process_and_form_keys_carry_the_app_prefix(self) -> None:
        self.assertEqual(self.process.get("id"), "nghi-phep.don")
        self.assertEqual(self.process.get("isExecutable"), "true")
        start = self.process.findall("b:startEvent", NS)
        task = self.process.findall("b:userTask", NS)
        self.assertEqual((len(start), len(task)), (1, 2))
        self.assertEqual(start[0].get(FLOWABLE + "formKey"), "nghi-phep.don")
        self.assertEqual(start[0].get(FLOWABLE + "initiator"), "initiator")
        self.assertEqual([t.get(FLOWABLE + "formKey") for t in task], ["nghi-phep.duyet"] * 2)
        self.assertEqual([t.get("name") for t in task], ["Trưởng phòng duyệt", "Hiệu trưởng duyệt"])
        manifest = (APP / "app.yaml").read_text(encoding="utf-8")
        self.assertIn("processes: [workflow/don-nghi-phep.bpmn20.xml]", manifest)
        for key in ("nghi-phep.don", "nghi-phep.duyet"):
            self.assertRegex(manifest, rf"\n    {re.escape(key)}: forms/\w+\.json\n")

    def test_reviewers_are_the_managers_of_the_requesters_department(self) -> None:
        task, principal = self.process.findall("b:userTask", NS)
        self.assertEqual(task.get(FLOWABLE + "candidateGroups"), GROUP)
        self.assertEqual(principal.get(FLOWABLE + "candidateGroups"), PRINCIPAL)
        self.assertIsNone(task.get(FLOWABLE + "assignee"))
        self.assertIsNone(principal.get(FLOWABLE + "assignee"))
        # cùng tên biến, cùng dạng nhóm với bước duyệt cấp phòng của văn bản đi (lõi đặt tenantId, departmentId)
        office = ET.parse(OFFICE).getroot()
        groups = {t.get(FLOWABLE + "candidateGroups") for t in office.iter(MODEL + "userTask")}
        self.assertIn(GROUP, groups)

    def outcomes(self, gateway: ET.Element) -> dict[tuple[str, str | None], str]:
        """(quyết định, phép so số ngày hoặc None) → tên bước đích, cho mọi luồng ra của một cổng."""
        names = {el.get("id"): el.get("name") for el in self.process}
        seen = {}
        for flow in (f for f in self.process.findall("b:sequenceFlow", NS) if f.get("sourceRef") == gateway.get("id")):
            cond = flow.find("b:conditionExpression", NS)
            m = CONDITION.fullmatch((cond.text or "").strip())
            self.assertIsNotNone(m, f"điều kiện của {flow.get('id')} phải là ${{quyetDinh == 'hằng'}} [&& soNgayLam …]")
            seen[(m.group(1), m.group(2))] = names[flow.get("targetRef")]
        return seen

    def test_gateways_cover_every_decision_of_the_review_form(self) -> None:
        duyet = json.loads((APP / "forms" / "duyet.json").read_text(encoding="utf-8"))
        don = json.loads((APP / "forms" / "don.json").read_text(encoding="utf-8"))
        manager, principal = self.process.findall("b:exclusiveGateway", NS)
        self.assertEqual(self.outcomes(manager), {("dong-y", "<="): "Đã duyệt", ("dong-y", ">"): "Hiệu trưởng duyệt",
                                                  ("tu-choi", None): "Bị từ chối"})
        self.assertEqual(self.outcomes(principal), {("dong-y", None): "Đã duyệt", ("tu-choi", None): "Bị từ chối"})
        self.assertEqual(sorted(duyet["properties"]["quyetDinh"]["enum"]), ["dong-y", "tu-choi"])
        self.assertIn("quyetDinh", duyet["required"])
        # số ngày so bằng số: trường số nguyên bắt buộc, Flowable không phải đổi chuỗi sang số lúc chạy
        self.assertEqual(don["properties"]["soNgayLam"]["type"], "integer")
        self.assertIn("soNgayLam", don["required"])

    def test_overdue_review_moves_to_the_principal(self) -> None:
        (timer,) = self.process.findall("b:boundaryEvent", NS)
        self.assertEqual(timer.get("attachedToRef"), "duyet")
        self.assertEqual(timer.get("cancelActivity"), "true")
        self.assertEqual(timer.findtext("b:timerEventDefinition/b:timeDuration", namespaces=NS).strip(), "P2D")
        (out,) = [f for f in self.process.findall("b:sequenceFlow", NS) if f.get("sourceRef") == timer.get("id")]
        self.assertEqual(out.get("targetRef"), "duyetHieuTruong")

    def test_every_node_is_on_a_path_from_start_to_an_end(self) -> None:
        nodes = {el.get("id"): tag(el) for el in self.process if tag(el) != "sequenceFlow"}
        edges = [(f.get("sourceRef"), f.get("targetRef")) for f in self.process.findall("b:sequenceFlow", NS)]
        # timer chạy khi việc nó gắn đang mở: coi như một cạnh từ việc đó
        edges += [(b.get("attachedToRef"), b.get("id")) for b in self.process.findall("b:boundaryEvent", NS)]
        for a, b in edges:
            self.assertIn(a, nodes)
            self.assertIn(b, nodes)

        def reach(start: set[str], pairs: list[tuple[str, str]]) -> set[str]:
            seen, todo = set(start), list(start)
            while todo:
                n = todo.pop()
                for a, b in pairs:
                    if a == n and b not in seen:
                        seen.add(b)
                        todo.append(b)
            return seen

        starts = {i for i, t in nodes.items() if t == "startEvent"}
        ends = {i for i, t in nodes.items() if t == "endEvent"}
        self.assertEqual(reach(starts, edges), set(nodes))
        self.assertEqual(reach(ends, [(b, a) for a, b in edges]), set(nodes))
        self.assertEqual(len(ends), 2)

    def test_diagram_draws_every_node_and_flow(self) -> None:
        drawn = {s.get("bpmnElement") for s in self.root.iter("{" + NS["di"] + "}BPMNShape")}
        drawn |= {e.get("bpmnElement") for e in self.root.iter("{" + NS["di"] + "}BPMNEdge")}
        ids = {el.get("id") for el in self.process if el.get("id")}
        self.assertEqual(drawn, ids)


if __name__ == "__main__":
    unittest.main()
