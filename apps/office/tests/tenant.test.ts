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

import assert from 'node:assert/strict'
import { test } from 'node:test'
import { tenantNames } from '../app/utils/tenant.ts'

test('thanh trên: tên ngắn của đơn vị nếu có, không thì tên đầy đủ; tên đầy đủ luôn giữ (#466)', () => {
  const full = 'Trường Công nghệ thông tin và Truyền thông'
  assert.deepEqual(tenantNames({ name: full, short_name: 'Trường CNTT & TT' }), { full, short: 'Trường CNTT & TT' })
  assert.deepEqual(tenantNames({ name: ' Trường Kinh tế ', short_name: null }), {
    full: 'Trường Kinh tế', short: 'Trường Kinh tế',
  })
  // lõi trước #466 không có cột: chỉ có name
  assert.deepEqual(tenantNames({ name: 'Trường Kinh tế' }), { full: 'Trường Kinh tế', short: 'Trường Kinh tế' })
  assert.deepEqual(tenantNames({ name: 'Trường Kinh tế', short_name: '  ' }).short, 'Trường Kinh tế')
  for (const row of [null, undefined, {}, { name: null, short_name: null }]) {
    assert.deepEqual(tenantNames(row), { full: '', short: '' })
  }
})
