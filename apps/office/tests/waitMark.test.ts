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


// Nhịp chờ của trợ lý (WaitMark): đúng hai nét của biểu tượng Liền mạch, mọi chuyển động chỉ chạy khi máy không bật
// giảm chuyển động, và hai khối chờ của trang Hỏi đáp (đang tìm, đang soạn) dùng nó thay vòng xoay.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const source = (file: string) => readFileSync(new URL(file, import.meta.url), 'utf8')
const mark = source('../app/components/WaitMark.vue')
const page = source('../app/pages/hoi-dap.vue')

test('WaitMark vẽ đúng hai nét của biểu tượng thương hiệu', () => {
  const symbol = source('../public/brand/signet-symbol.svg')
  const paths = [...symbol.matchAll(/<path d="([^"]+)"/g)].map((m) => m[1])
  assert.equal(paths.length, 2)
  for (const d of paths) assert.ok(mark.includes(`d="${d}"`), d)
  // hai nét cùng màu: màu nét chỉ đến từ currentColor, không tô riêng từng nét
  assert.doesNotMatch(mark, /<path[^>]*\b(stroke|fill|class)=/)
  assert.doesNotMatch(mark, /filter|drop-shadow|box-shadow/)
})

test('chuyển động chỉ chạy khi không bật giảm chuyển động', () => {
  const style = mark.slice(mark.indexOf('<style'))
  const open = style.indexOf('@media (prefers-reduced-motion: no-preference)')
  assert.ok(open > 0)
  const close = style.indexOf('@media (forced-colors: active)')
  const outside = style.slice(0, open) + style.slice(close)
  assert.doesNotMatch(outside, /animation:\s*wait-mark/)
})

test('hai khối chờ của Hỏi đáp dùng WaitMark, không còn vòng xoay', () => {
  assert.doesNotMatch(page, /animate-spin/)
  assert.match(page, /<WaitMark motion="trace">\{\{ t\('assist\.searching'\) \}\}<\/WaitMark>/)
  assert.match(page, /<WaitMark motion="breathe" stamp\b/)
})
