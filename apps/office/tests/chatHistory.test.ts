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

// Lịch sử trò chuyện của trang Hỏi đáp (utils/chatHistory.ts): lưu trong trình duyệt theo tài khoản, đọc lại có kiểm
// dạng, giới hạn số cuộc, hết chỗ thì bỏ cuộc cũ, đăng xuất xóa hết.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import type { Chat } from '../app/utils/chatHistory.ts'

const {
  HISTORY_PREFIX, MAX_CHATS, MAX_CHAT_TURNS, TITLE_CHARS,
  dropChat, dropChatHistory, historyKey, newChatId, putChat, readChats, titleOf, writeChats,
} = await import('../app/utils/chatHistory.ts')

class MemoryStore {
  data = new Map<string, string>()
  quota: number
  constructor(quota = Infinity) { this.quota = quota }
  get length() { return this.data.size }
  key(i: number) { return [...this.data.keys()][i] ?? null }
  getItem(k: string) { return this.data.get(k) ?? null }
  setItem(k: string, v: string) {
    if (v.length > this.quota) throw new Error('QuotaExceededError')
    this.data.set(k, v)
  }
  removeItem(k: string) { this.data.delete(k) }
}

const result = (askId: string) => ({ ask_id: askId, status: 'answered', answer: null, extract: null, sources: [],
  semantic: false, ai_available: true, warnings: [], duration_ms: 100 })
const turn = (q: string, askId = q) => ({ question: q, direction: '' as const, year: null, document: null,
  result: result(askId) as unknown as Chat['turns'][number]['result'] })
const chat = (id: string, updated: number, n = 1): Chat => ({ id, title: titleOf(`Câu ${id}`), updated,
  turns: Array.from({ length: n }, (_, i) => turn(`Câu ${id}.${i}`)) })

test('mỗi tài khoản một khóa; lưu, đọc lại, mới nhất trước', () => {
  const store = new MemoryStore()
  const me = historyKey('t-1', 'u-van-thu')
  const other = historyKey('t-1', 'u-khac')
  assert.equal(me, `${HISTORY_PREFIX}t-1:u-van-thu`)
  assert.equal(historyKey(null, 'u'), `${HISTORY_PREFIX}-:u`)
  putChat(store, me, chat('a', 1))
  putChat(store, me, chat('b', 2))
  assert.deepEqual(readChats(store, me).map((c) => c.id), ['b', 'a'])
  assert.deepEqual(readChats(store, other), [])
  // lưu lại cùng một cuộc thì thay, không thêm
  putChat(store, me, { ...chat('a', 3), turns: [turn('x'), turn('y')] })
  assert.deepEqual(readChats(store, me).map((c) => [c.id, c.turns.length]), [['a', 2], ['b', 1]])
  assert.deepEqual(dropChat(store, me, 'a').map((c) => c.id), ['b'])
})

test('đọc lại có kiểm dạng: hỏng, sai dạng, lượt thiếu kết quả thì bỏ, không lỗi', () => {
  const store = new MemoryStore()
  const key = historyKey('t', 'u')
  store.setItem(key, '{không phải JSON')
  assert.deepEqual(readChats(store, key), [])
  store.setItem(key, JSON.stringify({ id: 'x' }))
  assert.deepEqual(readChats(store, key), [])
  store.setItem(key, JSON.stringify([
    null, { id: 1 }, { id: 'rong', title: 'r', updated: 1, turns: [] },
    { id: 'ok', title: 't', updated: 2, turns: [{ question: 'Q?', result: null }, turn('Q2'),
      { ...turn('Q3'), direction: 'sai', year: '2026', document: { id: 7 } }] },
  ]))
  const [only, ...rest] = readChats(store, key)
  assert.equal(rest.length, 0)
  assert.deepEqual(only!.turns.map((t) => [t.question, t.direction, t.year, t.document]),
    [['Q2', '', null, null], ['Q3', '', null, null]])
  const blocked = { getItem() { throw new Error('SecurityError') }, setItem() {}, removeItem() {} }
  assert.deepEqual(readChats(blocked, key), [])
})

test('giới hạn số cuộc, số lượt; hết chỗ thì bỏ dần cuộc cũ nhất', () => {
  const store = new MemoryStore()
  const key = historyKey('t', 'u')
  for (let i = 0; i < MAX_CHATS + 5; i++) putChat(store, key, chat(`c${i}`, i))
  const kept = readChats(store, key)
  assert.equal(kept.length, MAX_CHATS)
  assert.equal(kept[0]!.id, `c${MAX_CHATS + 4}`)
  putChat(store, key, chat('dai', 999, MAX_CHAT_TURNS + 3))
  assert.equal(readChats(store, key)[0]!.turns.length, MAX_CHAT_TURNS)
  const one = JSON.stringify([chat('x', 1)]).length
  const small = new MemoryStore(one * 2 + 10)
  const got = writeChats(small, key, [chat('a', 1), chat('b', 2), chat('c', 3)])
  assert.deepEqual(got.map((c) => c.id), ['c', 'b'])
  assert.deepEqual(writeChats(new MemoryStore(5), key, [chat('a', 1)]), [])
})

test('tiêu đề là câu hỏi đầu, cắt ngắn; mã cuộc không trùng', () => {
  assert.equal(titleOf('  Điều kiện   xét học bổng là gì? '), 'Điều kiện xét học bổng là gì?')
  const long = titleOf('x'.repeat(200))
  assert.equal(long.length, TITLE_CHARS)
  assert.ok(long.endsWith('…'))
  assert.notEqual(newChatId(), newChatId())
})

test('đăng xuất xóa lịch sử của mọi tài khoản, không đụng khóa khác', () => {
  const store = new MemoryStore()
  putChat(store, historyKey('t', 'a'), chat('a', 1))
  putChat(store, historyKey('t', 'b'), chat('b', 1))
  store.setItem('moc.locale', 'vi')
  dropChatHistory(store)
  assert.deepEqual([...store.data.keys()], ['moc.locale'])
  dropChatHistory({ get length(): number { throw new Error('SecurityError') }, key: () => null, removeItem() {} })
  const auth = readFileSync(new URL('../app/composables/useAuth.ts', import.meta.url), 'utf8')
  assert.match(auth, /async function logout\(\)[\s\S]*?dropChatHistory\(\)[\s\S]*?signoutRedirect/)
})

test('trang Hỏi đáp lưu, mở lại, xóa cuộc trò chuyện; câu ghi chú nói lưu ở trình duyệt', () => {
  const page = readFileSync(new URL('../app/pages/hoi-dap.vue', import.meta.url), 'utf8')
  for (const name of ['<AssistHistory', 'putChat(', 'readChats(', 'dropChat(', 'openChat(', 'freshChat(']) {
    assert.ok(page.includes(name), name)
  }
  const vi = JSON.parse(readFileSync(new URL('../app/locales/vi.json', import.meta.url), 'utf8'))
  const en = JSON.parse(readFileSync(new URL('../app/locales/en.json', import.meta.url), 'utf8'))
  assert.match(vi.assist.historyNote, /trình duyệt/)
  assert.match(en.assist.historyNote, /browser/)
  assert.deepEqual(Object.keys(vi.assist.chats).sort(), Object.keys(en.assist.chats).sort())
})
