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

"""Sơ đồ một quy trình: hình từ BPMN DI của tệp, trạng thái từng bước từ lịch sử của Flowable (#603).

Giao diện vẽ SVG từ kết quả này, không cần thư viện BPMN (bpmn-js không theo giấy phép OSI). Bố cục đọc từ tệp
trong image chứ không từ bản đã deploy: phiên cũ chạy trên bản chưa có DI vẫn vẽ được, vì id phần tử không đổi.
shortcut: bố cục lấy từ tệp hiện hành; bản sau đổi id phần tử thì đọc DI theo processDefinitionId của phiên.
"""

from __future__ import annotations

import functools
import pathlib
from typing import Any
from xml.etree import ElementTree

MODEL = "{http://www.omg.org/spec/BPMN/20100524/MODEL}"
BPMNDI = "{http://www.omg.org/spec/BPMN/20100524/DI}"
DC = "{http://www.omg.org/spec/DD/20100524/DC}"
DI = "{http://www.omg.org/spec/DD/20100524/DI}"
MARGIN = 20


@functools.lru_cache(maxsize=None)
def layout(path: pathlib.Path) -> dict[str, Any]:
    """Hình và đường của quy trình trong tệp; chỉ đọc, kết quả dùng chung giữa các lần gọi."""
    # tệp do mình viết, nằm trong image (không phải đầu vào người dùng) nên không cần chặn DOCTYPE như apps/bpmn.py
    root = ElementTree.parse(path).getroot()
    process = root.find(f"{MODEL}process")
    elements = {el.get("id"): el for el in process if el.get("id")}
    nodes: dict[str, dict[str, Any]] = {}
    edges: dict[str, dict[str, Any]] = {}
    for shape in root.iter(f"{BPMNDI}BPMNShape"):
        el = elements.get(shape.get("bpmnElement"))
        bounds = shape.find(f"{DC}Bounds")
        if el is None or bounds is None:
            continue
        x, y, w, h = (float(bounds.get(k)) for k in ("x", "y", "width", "height"))
        nodes[el.get("id")] = {"kind": el.tag.removeprefix(MODEL), "name": el.get("name"), "x": x, "y": y, "w": w, "h": h}
    for edge in root.iter(f"{BPMNDI}BPMNEdge"):
        el = elements.get(edge.get("bpmnElement"))
        if el is None:
            continue
        points = [float(p.get(k)) for p in edge.iter(f"{DI}waypoint") for k in ("x", "y")]
        edges[el.get("id")] = {"name": el.get("name"), "points": points}
    xs = [n["x"] + n["w"] for n in nodes.values()] + [v for e in edges.values() for v in e["points"][0::2]]
    ys = [n["y"] + n["h"] for n in nodes.values()] + [v for e in edges.values() for v in e["points"][1::2]]
    return {"key": process.get("id"), "width": max(xs, default=0) + MARGIN, "height": max(ys, default=0) + MARGIN,
            "nodes": nodes, "edges": edges}


def with_states(diagram: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Gắn ``state`` cho từng hình và đường theo historic activity instances của một phiên.

    ``active``: có lượt chưa xong (``endTime`` rỗng); ``done``: đã chạy qua; ``""``: chưa tới. Một bước quay lại
    (bị trả lại rồi trình lại) có lượt cũ đã xong và lượt mới đang chờ: ``active`` thắng. Đường đã đi là dòng
    ``sequenceFlow`` cùng id.
    """
    state: dict[str, str] = {}
    for row in rows:
        if row.get("endTime") is None:
            state[row["activityId"]] = "active"
        else:
            state.setdefault(row["activityId"], "done")
    return {
        "key": diagram["key"], "width": diagram["width"], "height": diagram["height"],
        "nodes": [{"id": i, **n, "state": state.get(i, "")} for i, n in diagram["nodes"].items()],
        "edges": [{"id": i, **e, "state": state.get(i, "")} for i, e in diagram["edges"].items()],
    }
