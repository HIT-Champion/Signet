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

"""Token tài khoản dịch vụ của svc-workflow (client credentials của Keycloak) để gọi API nội bộ của svc-files, và lỗi
chung khi gọi svc-files. Phần lõi: tệp đính kèm form của ứng dụng (apps/files.py) và Văn phòng (files.py) cùng dùng.
"""

from __future__ import annotations

import asyncio
import time

import httpx2


class FilesError(Exception):
    """svc-files không trả lời hoặc từ chối. code: ``detail.code`` trong thân lỗi của svc-files, nếu đọc được."""

    def __init__(self, message: str, status: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


class ServiceToken:
    """Access token của tài khoản dịch vụ; dùng lại tới gần lúc hết hạn.

    Hạn tính theo giờ thật (``time.time``) như ``exp`` của token, không theo ``time.monotonic``: đồng hồ monotonic đứng
    yên khi máy ngủ hay VM bị tạm dừng, thức dậy token đã hết hạn mà vẫn tưởng còn."""

    def __init__(self, keycloak_url: str, realm: str, client_id: str, client_secret: str, *,
                 transport: httpx2.AsyncBaseTransport | None = None) -> None:
        self._path = f"/realms/{realm}/protocol/openid-connect/token"
        self._form = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}
        self._http = httpx2.AsyncClient(base_url=keycloak_url, timeout=15, transport=transport)
        self._token = ""
        self._expires_at = 0.0
        self._lock = asyncio.Lock()          # nhiều lời gọi cùng lúc thấy token hết hạn: chỉ một lần hỏi Keycloak

    async def aclose(self) -> None:
        await self._http.aclose()

    def forget(self, token: str) -> None:
        """Bỏ ``token`` nếu vẫn đang giữ nó (lời gọi khác có thể đã lấy token mới): lần ``get`` sau lấy token mới."""
        if self._token == token:
            self._token = ""

    async def get(self) -> str:
        async with self._lock:
            if self._token and time.time() < self._expires_at:
                return self._token
            try:
                r = await self._http.post(self._path, data=self._form)
            except httpx2.HTTPError as exc:
                raise FilesError(f"Không gọi được Keycloak: {exc}") from exc
            if r.status_code != 200:
                raise FilesError(f"Keycloak từ chối tài khoản dịch vụ: HTTP {r.status_code}", r.status_code)
            body = r.json()
            self._token = body["access_token"]
            # trừ hao 30 giây: token không hết hạn giữa đường
            self._expires_at = time.time() + max(float(body.get("expires_in", 60)) - 30, 0)
            return self._token
