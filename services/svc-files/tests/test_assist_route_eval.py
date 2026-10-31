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
của bộ định tuyến. Sửa bộ chọn đường làm số câu đúng tăng thì nâng ``FLOOR`` lên theo; chạy với ``-s`` để in bảng và các
câu sai. ``evaluate`` chấm được mọi bộ chọn cùng chữ ký với ``route.route``, không riêng bộ luật."""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from svc_files.assist import route, vi

DATA = Path(__file__).parent / "data" / "assist_routes.jsonl"

# số câu đúng tối thiểu của mỗi đường (đo trên develop lúc thêm bộ đo)
FLOOR = {
    "van_ban": 43,
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


@dataclass
class Score:
    total: Counter[str] = field(default_factory=Counter)
    correct: Counter[str] = field(default_factory=Counter)
    wrong: list[tuple[str, str, str]] = field(default_factory=list)     # (nhãn, đường ra, câu hỏi)

    def report(self) -> str:
        lines = [f"{name:<14} {self.correct[name]:>3}/{self.total[name]:<3} "
                 f"{self.correct[name] / max(self.total[name], 1):.0%}" for name in route.ROUTES]
        ok, n = sum(self.correct.values()), sum(self.total.values())
        lines.append(f"{'tong':<14} {ok:>3}/{n:<3} {ok / max(n, 1):.0%}")
        lines += [f"  mong {want} · ra {got} · {q}" for want, got, q in self.wrong]
        return "\n".join(lines)


def evaluate(choose: Callable[[str], Any]) -> Score:
    """Chấm một bộ chọn đường bất kỳ cùng chữ ký với ``route.route``: nhận câu hỏi đã ``vi.normalize``, trả về đối
    tượng có ``.name`` (``route.Route``) hoặc tên đường (str). Dùng được cho bộ luật hiện tại và cho bước chọn ý định
    bằng mô hình sau này (giả lập mô hình trong test, hoặc chạy tay với mô hình thật)."""
    score = Score()
    for row in _rows():
        out = choose(vi.normalize(row["q"]))
        got = out if isinstance(out, str) else out.name
        score.total[row["route"]] += 1
        if got == row["route"]:
            score.correct[row["route"]] += 1
        else:
            score.wrong.append((row["route"], got, row["q"]))
    return score


def test_route_accuracy_floor() -> None:
    score = evaluate(route.route)
    report = score.report()
    print("\n" + report)
    below = {name: (score.correct[name], floor) for name, floor in FLOOR.items() if score.correct[name] < floor}
    assert not below, f"dưới mức sàn (đúng, sàn): {below}\n{report}"


def test_evaluate_accepts_any_chooser() -> None:
    """Bộ chấm không gắn với route.py: một bộ chọn trả về tên đường (str) cũng chấm được."""
    score = evaluate(lambda q: "van_ban")
    assert sum(score.total.values()) == len(_rows())
    assert score.correct["van_ban"] == score.total["van_ban"]
    assert score.correct["gioi_thieu"] == 0
