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

"""Route /rest/v1 tới PostgREST (#561): luôn qua can-token (PostgREST không kiểm iss, APISIX kiểm), bỏ tiền tố, chỉ
các phương thức PostgREST dùng. Kiểm chữ, không cần Docker. Chạy: python3 -m unittest discover -s scripts/tests."""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


def route(name: str) -> str:
    text = (ROOT / "platform" / "apisix" / "apisix.yaml").read_text(encoding="utf-8")
    routes = text.split("\nroutes:\n", 1)[1]
    block = re.search(rf"^  - id: {re.escape(name)}\n(.*?)(?=^  - id: |^\S|\Z)", routes, re.M | re.S)
    assert block, f"không có route {name}"
    return block.group(1)


class RestRouteTest(unittest.TestCase):
    def test_rest_needs_a_token(self) -> None:
        self.assertIn("    plugin_config_id: can-token\n", route("rest"))

    def test_rest_strips_the_prefix_and_keeps_only_its_methods(self) -> None:
        r = route("rest")
        self.assertIn('    uris: ["/rest/v1", "/rest/v1/*"]\n', r)
        self.assertIn('regex_uri: ["^/rest/v1/?(.*)$", "/$1"]', r)
        methods = re.search(r"^    methods: \[(.*)\]$", r, re.M)
        assert methods
        self.assertEqual(methods.group(1).split(", "), ["GET", "HEAD", "POST", "PATCH", "DELETE"])

    def test_prefix_rewrite(self) -> None:
        rx = re.compile(r"^/rest/v1/?(.*)$")
        for uri, want in (("/rest/v1", "/"), ("/rest/v1/", "/"), ("/rest/v1/yeu_cau", "/yeu_cau")):
            with self.subTest(uri=uri):
                self.assertEqual(rx.sub(r"/\1", uri), want)


if __name__ == "__main__":
    unittest.main()
