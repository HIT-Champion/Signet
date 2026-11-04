// Copyright 2026 Signet Team
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.
//
// SPDX-License-Identifier: Apache-2.0

// #586: nút In theo hợp đồng K4 với svc-files: đường lấy mẫu in của bảng qua /rest/v1, đường in PDF (chỉ id số
// nguyên dương), câu báo theo mã trả lời.

import assert from 'node:assert/strict'
import { test } from 'node:test'

import { setLocale } from '../public/i18n.js'
import { duong, duongIn, loiIn } from '../public/rest.js'

test('mẫu in của bảng: GET /rest/v1/mau_in?bang=eq.<bảng>&select=id,ten', () => {
  assert.equal(duong.mau('yeu_cau'), '/mau_in?bang=eq.yeu_cau&select=id,ten')
  assert.equal(duong.mau('a&b'), '/mau_in?bang=eq.a%26b&select=id,ten')
})

test('đường in: id và mẫu là số nguyên dương, khóa khác thì không có nút In', () => {
  assert.equal(duongIn('yeu_cau', 12, 3), '/api/sinh/yeu_cau/12/pdf?mau=3')
  for (const [id, mau] of [['12', 3], [12, '3'], [0, 3], [12, -1], [1.5, 3], [12, null],
    ['6f1c2d3e-0000-4000-8000-000000000000', 3], [2 ** 60, 3]]) {
    assert.equal(duongIn('yeu_cau', id, mau), null, `${id}, ${mau}`)
  }
})

test('câu báo khi in không được', () => {
  setLocale('vi')
  assert.equal(loiIn(404, { detail: { code: 'not_found', message: 'x' } }),
    'Không còn dòng hay mẫu in này, hoặc chúng thuộc đơn vị khác.')
  assert.match(loiIn(503, null), /^Máy dựng PDF đang bận/)
  assert.equal(loiIn(401, null), 'Phiên đăng nhập đã hết. Tải lại trang để đăng nhập lại.')
  assert.match(loiIn(403, null), /^Cổng bảo mật của Signet chặn/)     // WAF: không có JSON
  assert.equal(loiIn(400, null), 'Signet từ chối yêu cầu (HTTP 400).')
  assert.equal(loiIn(200, null), 'Signet từ chối yêu cầu (HTTP 200).')  // 200 mà không phải PDF
  setLocale('en')
  try {
    assert.equal(loiIn(404, null), 'This row or print template no longer exists, or belongs to another unit.')
  } finally {
    setLocale('vi')
  }
})
