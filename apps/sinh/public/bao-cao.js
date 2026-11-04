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

// Báo cáo động (#587): một báo cáo là một dòng của bảng sinh.bao_cao (bảng nguồn, cột nhóm, phép tính, cột số, kiểu
// hiện), người dùng khai báo bằng chính biểu mẫu chung. Module này kiểm khai báo theo mô tả API (không gửi truy vấn
// sai), dựng truy vấn gộp của PostgREST, gộp kết quả theo tháng khi cột nhóm là ngày, và tính các lát của biểu đồ
// tròn. Hàm thuần, không đụng trình duyệt: test bằng node --test.

import { t } from './i18n.js'
import { note } from './openapi.js'

export const BAO_CAO = 'bao_cao'

// Giá trị enum sinh.phep_tinh, sinh.kieu_hien (migration của #587), viết bằng \u vì test i18n coi chuỗi có dấu trong
// mã là chữ giao diện chưa dịch; tests/bao-cao.test.js kiểm chúng đúng là các chữ của migration
export const PHEP_TINH = Object.freeze({ '\u0111\u1ebfm': 'count', 't\u1ed5ng': 'sum', 'trung b\u00ecnh': 'avg' })
export const KIEU_HIEN = Object.freeze({ 'b\u1ea3ng': 'table', 'c\u1ed9t': 'bar', 'tr\u00f2n': 'pie' })

// Tám màu phân loại theo thứ tự cố định (dataviz, đạt kiểm mù màu trên nền trắng); lát thứ chín trở đi gộp vào "Khác"
export const MAU = Object.freeze(['#2a78d6', '#eb6834', '#1baf7a', '#eda100', '#e87ba4', '#008300', '#6250d6',
  '#e34948'])

const NUMBER = new Set(['integer', 'number'])
const sai = (message) => ({ ok: false, message })
const ten = (p, name) => note(p.description).label || name

/**
 * Khai báo (một dòng của bao_cao) → {ok: true, …} dùng được cho duongBaoCao, ketQua; sai thì {ok: false, message}.
 * Bảng phải có trong mô tả API; cột nhóm là enum (PG enum) hoặc ngày (date, timestamp); tổng, trung bình cần cột số.
 */
export function kiemKhaiBao(spec, row) {
  const bang = String(row?.bang ?? '').trim()
  const props = spec?.definitions?.[bang]?.properties
  if (!props) return sai(t('report.noTable', { table: bang }))
  const nhom = String(row.nhom ?? '').trim()
  const g = Object.hasOwn(props, nhom) ? props[nhom] : null
  if (!g) return sai(t('report.noColumn', { table: bang, column: nhom }))
  const giaTri = Array.isArray(g.enum) && g.enum.length ? [...g.enum] : null
  const format = String(g.format ?? '')
  if (!giaTri && format !== 'date' && !format.startsWith('timestamp')) {
    return sai(t('report.badGroup', { column: ten(g, nhom) }))
  }
  const phep = PHEP_TINH[String(row.phep_tinh ?? '').normalize('NFC')]
  if (!phep) return sai(t('report.badOp', { op: String(row.phep_tinh ?? '') }))
  let cot = null
  if (phep !== 'count') {
    cot = String(row.cot_so ?? '').trim()
    if (!cot) return sai(t('report.needNumber'))
    if (!Object.hasOwn(props, cot)) return sai(t('report.noColumn', { table: bang, column: cot }))
    if (!NUMBER.has(props[cot].type)) return sai(t('report.badNumber', { column: ten(props[cot], cot) }))
  }
  return {
    ok: true, bang, nhom, phep, cot, giaTri,
    gio: format === 'timestamp with time zone',   // tháng tính theo giờ Việt Nam; timestamp không múi giờ thì cắt chuỗi
    kieu: KIEU_HIEN[String(row.kieu_hien ?? '').normalize('NFC')] ?? 'table',
    tenNhom: ten(g, nhom),
    tenCot: cot && ten(props[cot], cot),
  }
}

/** Đường của truy vấn gộp (sau /rest/v1). Cột nhóm là ngày thì PostgREST gộp theo ngày, ketQua cộng dồn theo tháng;
 *  trung bình theo tháng tính từ sum và count nên xin hai số đó thay vì avg. */
export function duongBaoCao(kb) {
  const cot = kb.cot && encodeURIComponent(kb.cot)
  const gop = {
    count: 'count()',
    sum: `${cot}.sum()`,
    avg: kb.giaTri ? `${cot}.avg()` : `${cot}.sum(),${cot}.count()`,
  }[kb.phep]
  return `/${encodeURIComponent(kb.bang)}?select=${encodeURIComponent(kb.nhom)},${gop}`
}

const THANG_VN = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit' })

/** Giá trị cột ngày → 'YYYY-MM' (timestamp theo giờ Việt Nam); trống hay sai → null. */
export function thang(value, gio) {
  if (typeof value !== 'string' || !/^\d{4}-\d{2}/.test(value)) return null
  if (!gio) return value.slice(0, 7)
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return null
  const p = Object.fromEntries(THANG_VN.formatToParts(d).map((x) => [x.type, x.value]))
  return `${p.year}-${p.month}`
}

/**
 * Các dòng PostgREST trả (mỗi nhóm một dòng có count, sum hay avg) → [{nhan, giaTri}] theo thứ tự hiện:
 *  - nhóm enum: đủ mọi giá trị theo thứ tự của enum (nhóm không có dòng là 0, trung bình là null), rồi giá trị lạ;
 *  - nhóm ngày: cộng dồn theo tháng, tháng tăng dần; nhãn MM/YYYY;
 *  - dòng có cột nhóm trống đứng cuối, nhãn "(trống)".
 */
export function ketQua(kb, rows) {
  const khoa = kb.giaTri ? (v) => v ?? null : (v) => thang(v, kb.gio)
  const gop = new Map((kb.giaTri ?? []).map((v) => [v, { s: 0, n: 0, avg: null }]))
  for (const r of Array.isArray(rows) ? rows : []) {
    const k = khoa(r?.[kb.nhom])
    const o = gop.get(k) ?? { s: 0, n: 0, avg: null }
    o.n += Number(r.count ?? 0)
    o.s += Number(r.sum ?? 0)
    if (r.avg !== undefined && r.avg !== null) o.avg = Number(r.avg)
    gop.set(k, o)
  }
  const keys = [...gop.keys()].filter((k) => k !== null)
  if (!kb.giaTri) keys.sort()
  if (gop.has(null)) keys.push(null)
  const value = (o) => {
    if (kb.phep === 'count') return o.n
    if (kb.phep === 'sum') return o.s
    return kb.giaTri ? o.avg : (o.n ? o.s / o.n : null)
  }
  const nhan = (k) => {
    if (k === null) return t('report.blank')
    return kb.giaTri ? String(k) : `${k.slice(5, 7)}/${k.slice(0, 4)}`
  }
  return keys.map((k) => ({ nhan: nhan(k), giaTri: value(gop.get(k)) }))
}

/** Số theo ngôn ngữ, tối đa hai chữ số lẻ; null (trung bình của nhóm rỗng) là "—". */
export function so(value, lang) {
  if (value === null || !Number.isFinite(value)) return t('form.empty', {}, lang)
  return new Intl.NumberFormat(lang === 'en' ? 'en-US' : 'vi-VN', { maximumFractionDigits: 2 }).format(value)
}

/** Độ dài thanh của biểu đồ cột, phần trăm so với nhóm lớn nhất; số âm, null là 0. */
export function thanh(items) {
  const max = Math.max(0, ...items.map((x) => x.giaTri ?? 0))
  return items.map((x) => (max > 0 ? (Math.max(0, x.giaTri ?? 0) / max) * 100 : 0))
}

/**
 * Biểu đồ tròn: {nen: conic-gradient(…), lat: [{nhan, giaTri, mau}]}; từ lát thứ chín gộp vào "Khác". Có số âm,
 * null hay tổng bằng 0 thì null: tròn không vẽ được, trang chỉ hiện bảng số.
 */
export function banhTron(items) {
  if (items.some((x) => x.giaTri === null || x.giaTri < 0)) return null
  let lat = items.filter((x) => x.giaTri > 0)
  const tong = lat.reduce((a, x) => a + x.giaTri, 0)
  if (!(tong > 0)) return null
  if (lat.length > MAU.length) {
    const khac = lat.slice(MAU.length - 1).reduce((a, x) => a + x.giaTri, 0)
    lat = [...lat.slice(0, MAU.length - 1), { nhan: t('report.other'), giaTri: khac }]
  }
  let den = 0
  const phan = []
  lat = lat.map((x, i) => {
    const tu = den
    den = i === lat.length - 1 ? 100 : den + (x.giaTri / tong) * 100
    phan.push(`${MAU[i]} ${+tu.toFixed(3)}% ${+den.toFixed(3)}%`)
    return { ...x, mau: MAU[i] }
  })
  return { nen: `conic-gradient(${phan.join(', ')})`, lat }
}
