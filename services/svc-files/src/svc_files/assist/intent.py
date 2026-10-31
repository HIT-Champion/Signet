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

"""Bước ý định bằng mô hình (LLM intent) của trợ lý hỏi đáp: mô hình đọc câu hỏi (và câu trước, nếu có) rồi chọn
đường trả lời, trước khi tìm văn bản.

- Đầu ra JSON ``{"y_dinh": <một trong INTENTS>, "can_cau_truoc": bool, "cau_hoi": "..."}``. Lượt đầu mô hình chỉ đọc
  câu hỏi: câu trước gửi kèm thì mô hình nhỏ hay kéo câu mới về chủ đề cũ ("Nộp đơn nghỉ phép ở đâu?" sau một câu về
  công văn thành câu hỏi văn bản). Mô hình nói câu hỏi cần câu trước mới hiểu ("còn điều 5 thì sao?") và có câu
  trước thì mới gọi lượt hai, kèm câu trước; ``cau_hoi`` của lượt hai là câu viết lại thành câu độc lập, chỉ dùng khi
  không có chỗ nào bị che (pii).
- Mô hình không trả lời câu hỏi ở bước này; chữ của câu hỏi nằm trong thẻ ``<cau_hoi>``, ``<cau_truoc>``.
- Mô hình không sẵn sàng, quá hạn, trả sai dạng → None: answer.py dùng bộ định tuyến luật (route.py) như trước.
- Kết quả giữ trong bộ nhớ theo (người hỏi, câu hỏi, câu trước) ``CACHE_TTL_S`` giây: giao diện gọi hai lượt (extract
  rồi generate) cho cùng câu hỏi, mô hình chỉ chọn đường một lần.
"""

from __future__ import annotations

import json
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from .. import pii
from . import grounding
from .ai import AiClient
from .route import Route

# ý định → (đường, mã lý do). Mã lý do của gioi_thieu trỏ mục chính của tệp Giới thiệu trợ lý (guide.INTRO_SECTIONS)
INTENTS: dict[str, tuple[str, str]] = {
    "tra_van_ban": ("van_ban", "tra-van-ban"),
    "huong_dan": ("huong_dan", "huong-dan"),
    "viec_cua_toi": ("viec_cua_toi", "viec-cua-toi"),
    "dem_van_ban": ("dem_van_ban", "dem-van-ban"),
    "chao_hoi": ("gioi_thieu", "xin-chao"),
    "cam_on": ("gioi_thieu", "cam-on"),
    "hoi_ve_tro_ly": ("gioi_thieu", "lam-duoc-gi"),
    "mo_hinh": ("gioi_thieu", "dung-mo-hinh"),
    "chua_ro": ("gioi_thieu", "luoi-an-toan"),
    "ngoai_pham_vi": ("ngoai_pham_vi", "ngoai-pham-vi"),
}
PREFIX = "llm:"
MAX_QUESTION = 500
CACHE_SIZE = 512
CACHE_TTL_S = 600.0

SYSTEM = (
    "Bạn phân loại câu hỏi gửi trợ lý hỏi đáp của Signet, phần mềm văn phòng điện tử của một trường đại học (văn bản "
    "đến, văn bản đi, trình ký, giao việc, hồ sơ công việc, đơn nghỉ phép). Câu hỏi nằm trong thẻ <cau_hoi>, câu hỏi "
    "lượt trước (nếu có) trong thẻ <cau_truoc>. Không trả lời câu hỏi. Chọn đúng một y_dinh:\n"
    "- tra_van_ban: hỏi nội dung văn bản, quy định, công văn, thông tư, quyết định trong kho; hỏi văn bản về một chủ "
    "đề (\"Điều kiện xét học bổng là gì?\", \"Công văn 131/ĐT-ĐHM yêu cầu gì?\", \"Có văn bản nào về tuyển sinh?\");\n"
    "- huong_dan: hỏi cách dùng phần mềm Signet: đăng nhập, đổi mật khẩu, trình ký, giao việc, chuyển xử lý, nộp đơn "
    "nghỉ phép, trang hay nút nằm ở đâu;\n"
    "- viec_cua_toi: hỏi việc được giao cho chính người hỏi, việc sắp hoặc đã quá hạn;\n"
    "- dem_van_ban: hỏi số lượng văn bản, hoặc liệt kê văn bản theo loại, theo thời gian, không nêu chủ đề nội dung "
    "(\"Có bao nhiêu công văn đến tháng này?\", \"Hệ thống có những văn bản nào?\");\n"
    "- chao_hoi: lời chào;\n"
    "- cam_on: cảm ơn, khen;\n"
    "- hoi_ve_tro_ly: hỏi trợ lý là ai, làm được gì, giúp được gì, nên hỏi thế nào;\n"
    "- mo_hinh: hỏi trợ lý dùng mô hình AI nào, giới hạn của trợ lý;\n"
    "- chua_ro: câu quá ngắn hoặc không rõ muốn hỏi gì;\n"
    "- ngoai_pham_vi: không liên quan văn bản của trường hay phần mềm Signet (thời tiết, giải toán, nấu ăn, kiến thức "
    "chung, viết mã, tin tức).\n"
    "can_cau_truoc: true khi câu hỏi nhắc tới điều chưa nói rõ trong chính câu (\"nó\", \"văn bản đó\", \"điều này\", "
    "\"còn ... thì sao\") nên cần câu hỏi trước mới hiểu; false khi câu tự đủ nghĩa.\n"
    "cau_hoi: nếu có <cau_truoc>, viết lại câu hỏi thành một câu đầy đủ theo câu trước; nếu không, chép nguyên câu "
    'hỏi. Chỉ trả JSON {"y_dinh": "...", "can_cau_truoc": true hoặc false, "cau_hoi": "..."}. /no_think'
)
FORMAT: dict[str, Any] = {
    "type": "object",
    "properties": {"y_dinh": {"type": "string", "enum": list(INTENTS)}, "can_cau_truoc": {"type": "boolean"},
                   "cau_hoi": {"type": "string"}},
    "required": ["y_dinh", "can_cau_truoc", "cau_hoi"],
}
OPTIONS: dict[str, Any] = {"temperature": 0.0, "num_ctx": 2048, "num_predict": 160, "seed": 7}


@dataclass(frozen=True)
class Understood:
    route: Route
    rewritten: str | None       # câu nối tiếp đã viết lại thành câu độc lập; None: dùng nguyên câu hỏi
    intent: str
    needs_previous: bool = False    # mô hình nói câu hỏi cần câu trước mới hiểu


def messages(question: str, previous: str | None) -> list[dict[str, str]]:
    user = f"<cau_hoi>\n{grounding.clean(question)}\n</cau_hoi>"
    if previous:
        user = f"<cau_truoc>\n{grounding.clean(previous)}\n</cau_truoc>\n" + user
    return [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]


def parse(content: str | None, question: str, previous: str | None, lang: str, *,
          masked: bool) -> Understood | None:
    """Đầu ra của mô hình → Understood; sai dạng → None. ``lang``: ngôn ngữ bộ luật đoán (chọn bản Giới thiệu)."""
    try:
        got = json.loads(content or "")
    except (ValueError, TypeError):
        return None
    if not isinstance(got, dict) or got.get("y_dinh") not in INTENTS or not isinstance(got.get("cau_hoi"), str):
        return None
    name, reason = INTENTS[got["y_dinh"]]
    text = " ".join(got["cau_hoi"].split())
    rewritten = None
    if previous and not masked and text and len(text) <= MAX_QUESTION and text.casefold() != question.casefold():
        rewritten = text
    return Understood(Route(name, PREFIX + reason, lang), rewritten, got["y_dinh"], got.get("can_cau_truoc") is True)


class IntentStep:
    """Gọi mô hình chọn đường; giữ kết quả theo người hỏi để lượt generate không gọi lại."""

    def __init__(self, ai: AiClient, *, timeout_s: float, clock=time.monotonic) -> None:
        self.ai = ai
        self.timeout_s = timeout_s
        self._clock = clock
        self._cache: OrderedDict[tuple[str, str, str], tuple[float, Understood]] = OrderedDict()

    async def understand(self, user_id: str, question: str, previous: str | None, lang: str, *,
                         timeout_s: float) -> Understood | None:
        key = (user_id, question, previous or "")
        now = self._clock()
        hit = self._cache.get(key)
        if hit is not None and now - hit[0] < CACHE_TTL_S:
            self._cache.move_to_end(key)
            return hit[1]
        if not self.ai.chat_available or timeout_s <= 0:
            return None
        end = now + min(self.timeout_s, timeout_s)
        masker = pii.Masker()
        asked = masker.mask(question).text
        result = await self.ai.chat(messages(asked, None), format=FORMAT, options=OPTIONS, timeout_s=end - now)
        got = parse(result.content, question, None, lang, masked=False)
        if got is not None and got.needs_previous and previous and end - self._clock() > 0:
            before = masker.mask(previous).text
            result = await self.ai.chat(messages(asked, before), format=FORMAT, options=OPTIONS,
                                        timeout_s=end - self._clock())
            second = parse(result.content, question, previous, lang, masked=masker.total > 0)
            got = second if second is not None else got
        if got is not None:
            self._cache[key] = (now, got)
            while len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)
        return got
