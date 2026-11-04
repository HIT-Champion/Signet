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

// Gọi /rest/v1 (PostgREST sau APISIX, #560): dựng địa chỉ và tham số fetch, đọc trả lời. Phần thuần, không đụng
// trình duyệt: test bằng node --test. Token Keycloak của người dùng; PostgREST đặt vai trò, đơn vị từ claim, RLS của
// khung CSDL lọc dòng. Không có vai trò ẩn danh: thiếu token là 401.

import { t } from './i18n.js'

export const API = '/rest/v1'
// shortcut: chỉ tải PAGE dòng mới nhất, không phân trang; bảng lớn hơn thì thêm nút "xem thêm" theo Content-Range
export const PAGE = 50

const tableUrl = (table) => `/${encodeURIComponent(table)}`

export const duong = {
  spec: () => '/',
  // created_at là cột chuẩn khung CSDL thêm vào mọi bảng
  rows: (table) => `${tableUrl(table)}?order=created_at.desc&limit=${PAGE}`,
  create: (table) => tableUrl(table),
  row: (table, key, value) => `${tableUrl(table)}?${encodeURIComponent(key)}=eq.${encodeURIComponent(String(value))}`,
  // mẫu in của bảng (#586, hợp đồng K4); bản cài chưa có bảng mau_in thì PostgREST trả 404
  mau: (table) => `/mau_in?bang=eq.${encodeURIComponent(table)}&select=id,ten`,
}

const soNguyen = (v) => Number.isSafeInteger(v) && v > 0

/** Đường in PDF một dòng theo mẫu (svc-files, #586): /api/sinh/<bảng>/<id>/pdf?mau=<id mẫu>. svc-files chỉ nhận id
 *  là số nguyên dương: khóa khác (uuid) thì null, trang không hiện nút In. */
export function duongIn(table, id, mau) {
  if (!soNguyen(id) || !soNguyen(mau)) return null
  return `/api/sinh/${encodeURIComponent(table)}/${id}/pdf?mau=${mau}`
}

/** Một lời gọi → [địa chỉ, tham số của fetch]. Ghi thì xin PostgREST trả lại dòng đã ghi; đọc danh sách thì xin
 *  tổng số dòng (Content-Range). */
export function yeuCau(token, method, path, data) {
  const headers = { Authorization: `Bearer ${token}`, Accept: 'application/json' }
  const init = { method, headers, cache: 'no-store' }
  if (data !== undefined) {
    headers['Content-Type'] = 'application/json'
    headers.Prefer = 'return=representation'
    init.body = JSON.stringify(data)
  } else if (method === 'GET' && path !== duong.spec()) {
    headers.Prefer = 'count=exact'
  }
  return [`${API}${path}`, init]
}

/** Thân trả lời dạng chữ → JSON; rỗng hay không phải JSON (trang lỗi của cổng) → null. */
export function docThan(text) {
  if (!text) return null
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

/** "0-49/120" → 120; "*" hay thiếu → null. */
export function tongSo(contentRange) {
  const m = /\/(\d+)$/.exec(String(contentRange ?? ''))
  return m ? Number(m[1]) : null
}

/** Mã trả lời (mang: không gọi được) → khóa câu báo; tests/i18n.test.js kiểm khóa có thật. 400 là CSDL từ chối
 *  (NOT NULL, CHECK, khung chặn): không đưa câu lỗi thô của PostgreSQL ra trang. */
export const LOI = Object.freeze({
  mang: 'error.network',
  400: 'error.invalid',
  401: 'error.session',
  403: 'error.forbidden',
  404: 'error.gone',
  409: 'error.conflict',
  429: 'error.rateLimited',
  500: 'error.unavailable',
})

/** Trả lời → {ok: true, data} hoặc {ok: false, status, message}. 403 không kèm JSON của PostgREST là WAF ở cổng
 *  chặn nội dung gửi lên, không phải thiếu quyền. */
export function docTraLoi(status, body) {
  if (status >= 200 && status < 300) return { ok: true, data: body }
  if (status === 403 && body === null) return { ok: false, status, message: t('error.blocked') }
  const key = LOI[status] || (status >= 500 ? LOI[500] : '')
  return { ok: false, status, message: key ? t(key) : t('error.rejected', { status }) }
}

/** In không được → câu báo (K4): 404 là không có dòng hay mẫu, hoặc chúng thuộc đơn vị khác (RLS trả như nhau); 503
 *  là PostgREST chưa trả lời hoặc dựng PDF quá giờ. 2xx mà không phải PDF, hay 400 (trang tự dựng đường nên không
 *  gặp) thì báo kèm mã. */
export function loiIn(status, body) {
  if (status === 404) return t('print.notFound')
  if (status === 503) return t('print.busy')
  if (status < 300 || status === 400) return t('error.rejected', { status })
  return docTraLoi(status, body).message
}

/** Sửa một dòng: PostgREST trả mảng dòng đã ghi. Mảng rỗng là không có dòng nào khớp mà người dùng được ghi (đã
 *  xóa, hay RLS không cho), báo như 404. */
export function daSua(kq) {
  if (kq.ok && Array.isArray(kq.data) && !kq.data.length) return { ok: false, status: 404, message: t(LOI[404]) }
  return kq
}

const isMap = (v) => v !== null && typeof v === 'object' && !Array.isArray(v)

function claims(token) {
  try {
    const part = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')
    const c = JSON.parse(decodeURIComponent(Array.from(atob(part), (ch) =>
      '%' + ch.charCodeAt(0).toString(16).padStart(2, '0')).join('')))
    return isMap(c) ? c : null
  } catch {
    return null
  }
}

/** Tên người dùng trong access token (claim name, không thì preferred_username) — chỉ để chào, không để phân quyền. */
export function tenNguoi(token) {
  const c = claims(token)
  return c?.name || c?.preferred_username || ''
}

/** Thời điểm theo giờ Việt Nam, dạng 26/10/2026 14:05; sai thì rỗng. */
export function ngayGio(iso) {
  const d = new Date(iso)
  if (typeof iso !== 'string' || Number.isNaN(d.getTime())) return ''
  const p = new Intl.DateTimeFormat('vi-VN', { timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit',
    year: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }).formatToParts(d)
  const v = Object.fromEntries(p.map((x) => [x.type, x.value]))
  return `${v.day}/${v.month}/${v.year} ${v.hour}:${v.minute}`
}
