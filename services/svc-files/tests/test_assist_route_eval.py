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

"""Bộ đo độ chính xác của bộ định tuyến trợ lý (assist/route.py) trên tập câu hỏi có nhãn (data/assist_routes.jsonl).

Khác test_assist_route.py (từng câu phải đúng): ở đây câu sai được phép, test chỉ giữ một mức sàn cho mỗi đường để
sửa mẫu ở chỗ này không làm hỏng chỗ khác mà không ai biết. Nhãn là đường người hỏi mong đợi, không chép từ kết quả
của bộ định tuyến. Sửa route.py làm số câu đúng tăng thì nâng ``FLOOR`` lên theo; chạy với ``-s`` để in bảng và các
câu sai."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from svc_files.assist import route, vi

DATA = Path(__file__).parent / "data" / "assist_routes.jsonl"

# số câu đúng tối thiểu của mỗi đường (đo trên develop lúc thêm bộ đo)
FLOOR = {
    "van_ban": 42,
    "gioi_thieu": 22,
    "huong_dan": 19,
    "ngoai_pham_vi": 19,
    "viec_cua_toi": 14,
    "dem_van_ban": 15,
}


def _rows() -> list[dict[str, str]]:
    with DATA.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def test_dataset_is_well_formed() -> None:
    rows = _rows()
    assert len(rows) >= 150
    assert {r["route"] for r in rows} == set(route.ROUTES)
    questions = [r["q"] for r in rows]
    assert len(questions) == len(set(questions)), "câu hỏi trùng"
    assert set(FLOOR) == set(route.ROUTES)


def test_route_accuracy_floor() -> None:
    total: Counter[str] = Counter()
    correct: Counter[str] = Counter()
    wrong: list[tuple[str, str, str]] = []
    for row in _rows():
        got = route.route(vi.normalize(row["q"])).name
        total[row["route"]] += 1
        if got == row["route"]:
            correct[row["route"]] += 1
        else:
            wrong.append((row["route"], got, row["q"]))

    lines = [f"{name:<14} {correct[name]:>3}/{total[name]:<3} {correct[name] / total[name]:.0%}"
             for name in route.ROUTES]
    all_ok, all_n = sum(correct.values()), sum(total.values())
    lines.append(f"{'tong':<14} {all_ok:>3}/{all_n:<3} {all_ok / all_n:.0%}")
    lines += [f"  mong {want} · ra {got} · {q}" for want, got, q in wrong]
    report = "\n".join(lines)
    print("\n" + report)

    below = {name: (correct[name], floor) for name, floor in FLOOR.items() if correct[name] < floor}
    assert not below, f"dưới mức sàn (đúng, sàn): {below}\n{report}"
