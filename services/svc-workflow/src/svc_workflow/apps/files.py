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

"""Đọc tệp đính kèm form của ứng dụng (#325) từ svc-files: ``GET /internal/app-files/{id}?tenant=…`` bằng token tài
khoản dịch vụ của svc-workflow (svc-files không tin mạng nội bộ). api.py đã xét người xem trước khi gọi; svc-files chỉ
trả tệp thường của đúng thuê ước, tệp mã hóa hay gắn văn bản hạn chế thì 404.
"""

from __future__ import annotations

import uuid

import httpx2

from ..service_token import FilesError, ServiceToken


class AppFiles:
    def __init__(self, base_url: str, token: ServiceToken, *, timeout_s: float = 60.0,
                 transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self._token = token
        self._http = httpx2.AsyncClient(base_url=base_url, timeout=timeout_s, transport=transport)

    async def aclose(self) -> None:
        await self._http.aclose()
        await self._token.aclose()

    async def open(self, tenant_id: uuid.UUID, file_id: str) -> httpx2.Response:
        """Phản hồi đang mở: người gọi đọc ``aiter_bytes()`` rồi ``aclose()``. svc-files trả 401 (token hết hạn sớm
        hơn ta tính) thì lấy token mới, gửi lại đúng một lần. Lỗi → FilesError, ``status`` None khi không gọi được."""
        for attempt in (1, 2):
            token = await self._token.get()
            request = self._http.build_request("GET", f"/internal/app-files/{file_id}",
                                               params={"tenant": str(tenant_id)},
                                               headers={"Authorization": f"Bearer {token}"})
            try:
                r = await self._http.send(request, stream=True)
            except httpx2.HTTPError as exc:
                raise FilesError(f"Không gọi được svc-files: {exc}") from exc
            if r.status_code == 200:
                return r
            await r.aclose()
            if r.status_code != 401 or attempt == 2:
                break
            self._token.forget(token)
        raise FilesError(f"svc-files trả {r.status_code}", r.status_code)
