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

// Lịch sử trò chuyện của trang Hỏi đáp: chỉ lưu trong trình duyệt (localStorage), mỗi tài khoản một khóa
// "sg-hoi-dap:<đơn vị>:<người dùng>"; không gửi máy chủ. Mỗi cuộc giữ các lượt đã xong (câu hỏi, bộ lọc, kết quả cuối
// cùng của svc-files) để mở lại như lúc rời đi. Tối đa MAX_CHATS cuộc, mỗi cuộc MAX_CHAT_TURNS lượt (như trang); trình
// duyệt hết chỗ thì bỏ dần cuộc cũ nhất. Đăng xuất xóa hết (dropChatHistory, useAuth.logout). Dữ liệu đọc lại được
// kiểm dạng: hỏng hay sai dạng thì bỏ, không làm trang lỗi.

import type { AskResult } from '../composables/useApi'

export const HISTORY_PREFIX = 'sg-hoi-dap:'
export const MAX_CHATS = 20
export const MAX_CHAT_TURNS = 10
export const TITLE_CHARS = 60

export interface SavedTurn {
  question: string
  direction: '' | 'in' | 'out'
  year: number | null
  document: { id: string; label: string } | null
  previous?: string
  result: AskResult
}

export interface Chat {
  id: string
  title: string          // câu hỏi đầu tiên, cắt ngắn
  updated: number        // ms, lần cuối có lượt xong
  turns: SavedTurn[]
}

export type HistoryStore = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

export function historyKey(tenantId: string | null, userId: string): string {
  return `${HISTORY_PREFIX}${tenantId ?? '-'}:${userId}`
}

export function titleOf(question: string): string {
  const q = question.replace(/\s+/g, ' ').trim()
  return q.length > TITLE_CHARS ? `${q.slice(0, TITLE_CHARS - 1)}…` : q
}

export function newChatId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

function savedTurn(x: unknown): SavedTurn | null {
  if (!x || typeof x !== 'object') return null
  const t = x as Record<string, unknown>
  const result = t.result as Record<string, unknown> | null
  if (typeof t.question !== 'string' || !t.question || !result || typeof result !== 'object'
    || typeof result.ask_id !== 'string' || !Array.isArray(result.sources)) return null
  const doc = t.document as Record<string, unknown> | null
  return {
    question: t.question,
    direction: t.direction === 'in' || t.direction === 'out' ? t.direction : '',
    year: typeof t.year === 'number' ? t.year : null,
    document: doc && typeof doc.id === 'string' && typeof doc.label === 'string' ? { id: doc.id, label: doc.label } : null,
    ...(typeof t.previous === 'string' ? { previous: t.previous } : {}),
    result: result as unknown as AskResult,
  }
}

/** Các cuộc đã lưu của một tài khoản, mới nhất trước; không đọc được hay sai dạng thì bỏ. */
export function readChats(store: HistoryStore, key: string): Chat[] {
  let raw: string | null = null
  try {
    raw = store.getItem(key)
  } catch {
    return []        // trình duyệt chặn lưu trữ
  }
  if (!raw) return []
  let data: unknown
  try {
    data = JSON.parse(raw)
  } catch {
    return []
  }
  if (!Array.isArray(data)) return []
  const chats: Chat[] = []
  for (const c of data as Record<string, unknown>[]) {
    if (!c || typeof c.id !== 'string' || typeof c.title !== 'string' || typeof c.updated !== 'number'
      || !Array.isArray(c.turns)) continue
    const turns = c.turns.map(savedTurn).filter((x): x is SavedTurn => x !== null).slice(-MAX_CHAT_TURNS)
    if (turns.length) chats.push({ id: c.id, title: c.title, updated: c.updated, turns })
  }
  return chats.sort((a, b) => b.updated - a.updated).slice(0, MAX_CHATS)
}

/** Ghi danh sách (mới nhất trước, tối đa MAX_CHATS); hết chỗ thì bỏ dần cuộc cũ nhất. Trả về danh sách đã ghi. */
export function writeChats(store: HistoryStore, key: string, chats: Chat[]): Chat[] {
  let list = [...chats].sort((a, b) => b.updated - a.updated).slice(0, MAX_CHATS)
  while (list.length) {
    try {
      store.setItem(key, JSON.stringify(list))
      return list
    } catch {
      list = list.slice(0, -1)
    }
  }
  try { store.removeItem(key) } catch { /* trình duyệt chặn lưu trữ */ }
  return []
}

/** Lưu (thêm hoặc thay) một cuộc. */
export function putChat(store: HistoryStore, key: string, chat: Chat): Chat[] {
  const turns = chat.turns.slice(-MAX_CHAT_TURNS)
  if (!turns.length) return readChats(store, key)
  return writeChats(store, key, [{ ...chat, turns }, ...readChats(store, key).filter((c) => c.id !== chat.id)])
}

/** Xóa một cuộc. */
export function dropChat(store: HistoryStore, key: string, id: string): Chat[] {
  return writeChats(store, key, readChats(store, key).filter((c) => c.id !== id))
}

/** Đăng xuất: xóa lịch sử trò chuyện của mọi tài khoản trên trình duyệt này. */
export function dropChatHistory(store?: Pick<Storage, 'length' | 'key' | 'removeItem'> | null) {
  try {
    const s = store ?? (typeof localStorage === 'undefined' ? null : localStorage)
    if (!s) return
    const keys: string[] = []
    for (let i = 0; i < s.length; i++) {
      const k = s.key(i)
      if (k?.startsWith(HISTORY_PREFIX)) keys.push(k)
    }
    for (const k of keys) s.removeItem(k)
  } catch {
    // trình duyệt chặn lưu trữ: không có gì để xóa
  }
}
