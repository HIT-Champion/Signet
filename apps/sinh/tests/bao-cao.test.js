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

// #587: báo cáo động. Khai báo kiểm theo mô tả API thật của PostgREST v14 (bảng sinh.yeu_cau: trang_thai là enum,
// han là date, created_at là timestamptz) và mô tả viết tay (so_luong là cột số), truy vấn gộp theo dạng của hợp
// đồng K3, gộp theo tháng, lát của biểu đồ tròn.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

import {
  BAO_CAO, KIEU_HIEN, MAU, PHEP_TINH, banhTron, duongBaoCao, ketQua, kiemKhaiBao, so, thang, thanh,
} from '../public/bao-cao.js'
import { setLocale } from '../public/i18n.js'

const read = (name) => JSON.parse(readFileSync(new URL(name, import.meta.url), 'utf8'))
const real = read('postgrest-v14-openapi.json')
const hand = read('postgrest-openapi.json')
const kb = (spec, row) => {
  const out = kiemKhaiBao(spec, { phep_tinh: 'đếm', kieu_hien: 'cột', ...row })
  assert.equal(out.ok, true, out.message)
  return out
}

test('giá trị enum đúng chữ của migration sinh.phep_tinh, sinh.kieu_hien', () => {
  assert.equal(BAO_CAO, 'bao_cao')
  assert.deepEqual(PHEP_TINH, { 'đếm': 'count', 'tổng': 'sum', 'trung bình': 'avg' })
  assert.deepEqual(KIEU_HIEN, { 'bảng': 'table', 'cột': 'bar', 'tròn': 'pie' })
  // chữ dạng tổ hợp (NFD) cũng nhận
  assert.equal(kiemKhaiBao(real, { bang: 'yeu_cau', nhom: 'han', phep_tinh: 'đếm'.normalize('NFD') }).phep, 'count')
})

test('khai báo hợp lệ: nhóm theo enum, theo ngày, theo timestamptz; nhãn từ COMMENT', () => {
  const a = kb(real, { bang: 'yeu_cau', nhom: 'trang_thai' })
  assert.deepEqual([a.phep, a.cot, a.giaTri, a.gio, a.kieu, a.tenNhom], ['count', null, ['mới', 'đang xử lý', 'xong'],
    false, 'bar', 'Trạng thái'])
  const b = kb(real, { bang: 'yeu_cau', nhom: 'han', kieu_hien: 'tròn' })
  assert.deepEqual([b.giaTri, b.gio, b.kieu], [null, false, 'pie'])
  assert.equal(kb(real, { bang: 'yeu_cau', nhom: 'created_at' }).gio, true)
  const c = kb(hand, { bang: 'yeu_cau', nhom: 'trang_thai', phep_tinh: 'tổng', cot_so: ' so_luong ', kieu_hien: null })
  assert.deepEqual([c.phep, c.cot, c.kieu], ['sum', 'so_luong', 'table'])
})

test('khai báo sai: câu báo bằng chữ, không có truy vấn', () => {
  setLocale('vi')
  const loi = (row) => {
    const out = kiemKhaiBao(real, { bang: 'yeu_cau', nhom: 'trang_thai', phep_tinh: 'đếm', ...row })
    assert.equal(out.ok, false)
    return out.message
  }
  assert.equal(loi({ bang: 'khong_co' }), 'Không có bảng «khong_co» trong schema sinh.')
  assert.equal(loi({ bang: null }), 'Không có bảng «» trong schema sinh.')
  assert.equal(loi({ nhom: 'khong_co' }), 'Bảng «yeu_cau» không có cột «khong_co».')
  assert.equal(loi({ nhom: 'constructor' }), 'Bảng «yeu_cau» không có cột «constructor».')
  assert.match(loi({ nhom: 'tieu_de' }), /^Cột nhóm «Tiêu đề» phải là/)
  assert.match(loi({ nhom: 'tenant_id' }), /^Cột nhóm «tenant_id» phải là/)     // uuid: không phải enum hay ngày
  assert.equal(loi({ phep_tinh: 'đếm ngược' }), 'Không có phép tính «đếm ngược».')
  assert.equal(loi({ phep_tinh: 'tổng' }), 'Tính tổng hay trung bình thì cần điền cột số.')
  assert.equal(loi({ phep_tinh: 'trung bình', cot_so: 'so_luong' }), 'Bảng «yeu_cau» không có cột «so_luong».')
  assert.equal(loi({ phep_tinh: 'tổng', cot_so: 'han' }), 'Cột «Hạn xử lý» không phải cột số.')
  setLocale('en')
  try {
    assert.equal(loi({ bang: 'x' }), 'There is no table "x" in the sinh schema.')
  } finally {
    setLocale('vi')
  }
})

test('truy vấn gộp theo hợp đồng K3', () => {
  assert.equal(duongBaoCao(kb(real, { bang: 'yeu_cau', nhom: 'trang_thai' })), '/yeu_cau?select=trang_thai,count()')
  assert.equal(duongBaoCao(kb(hand, { bang: 'yeu_cau', nhom: 'trang_thai', phep_tinh: 'tổng', cot_so: 'so_luong' })),
    '/yeu_cau?select=trang_thai,so_luong.sum()')
  assert.equal(duongBaoCao(kb(hand, { bang: 'yeu_cau', nhom: 'trang_thai', phep_tinh: 'trung bình',
    cot_so: 'so_luong' })), '/yeu_cau?select=trang_thai,so_luong.avg()')
  // nhóm theo ngày: trung bình theo tháng tính từ tổng và số giá trị có (bỏ null như avg của PostgreSQL)
  assert.equal(duongBaoCao(kb(hand, { bang: 'yeu_cau', nhom: 'han', phep_tinh: 'trung bình', cot_so: 'so_luong' })),
    '/yeu_cau?select=han,so_luong.sum(),so_luong.count()')
  assert.equal(duongBaoCao(kb(real, { bang: 'yeu_cau', nhom: 'han' })), '/yeu_cau?select=han,count()')
})

test('nhóm enum: đủ giá trị theo thứ tự enum, nhóm không có dòng là 0, trống đứng cuối', () => {
  setLocale('vi')
  const k = kb(real, { bang: 'yeu_cau', nhom: 'trang_thai' })
  const rows = [{ trang_thai: 'xong', count: 4 }, { trang_thai: null, count: 1 }, { trang_thai: 'mới', count: 2 }]
  assert.deepEqual(ketQua(k, rows), [
    { nhan: 'mới', giaTri: 2 }, { nhan: 'đang xử lý', giaTri: 0 }, { nhan: 'xong', giaTri: 4 },
    { nhan: '(trống)', giaTri: 1 },
  ])
  const avg = kb(hand, { bang: 'yeu_cau', nhom: 'trang_thai', phep_tinh: 'trung bình', cot_so: 'so_luong' })
  assert.deepEqual(ketQua(avg, [{ trang_thai: 'Mới', avg: '2.5000000000000000' }]).map((x) => x.giaTri),
    [2.5, null, null])
  assert.deepEqual(ketQua(k, null).map((x) => x.giaTri), [0, 0, 0])
})

test('nhóm ngày: cộng dồn theo tháng, tháng tăng dần, trung bình có trọng số', () => {
  const k = kb(real, { bang: 'yeu_cau', nhom: 'han' })
  const rows = [
    { han: '2026-11-01', count: 4 }, { han: '2026-10-03', count: 2 }, { han: null, count: 3 },
    { han: '2026-10-20', count: 1 },
  ]
  assert.deepEqual(ketQua(k, rows), [
    { nhan: '10/2026', giaTri: 3 }, { nhan: '11/2026', giaTri: 4 }, { nhan: '(trống)', giaTri: 3 },
  ])
  assert.deepEqual(ketQua(k, []), [])
  const avg = kb(hand, { bang: 'yeu_cau', nhom: 'han', phep_tinh: 'trung bình', cot_so: 'so_luong' })
  // tháng 10: (10 + 2) / (3 + 1) = 3, không phải trung bình của hai trung bình (10/3 và 2)
  assert.deepEqual(ketQua(avg, [
    { han: '2026-10-03', sum: 10, count: 3 }, { han: '2026-10-20', sum: 2, count: 1 },
    { han: '2026-12-01', sum: null, count: 0 },
  ]), [{ nhan: '10/2026', giaTri: 3 }, { nhan: '12/2026', giaTri: null }])
})

test('timestamptz: tháng theo giờ Việt Nam', () => {
  assert.equal(thang('2026-10-31T17:30:00+00:00', true), '2026-11')
  assert.equal(thang('2026-10-31T16:59:59+00:00', true), '2026-10')
  assert.equal(thang('2026-10-31', false), '2026-10')
  for (const v of [null, '', 'abc', 42]) assert.equal(thang(v, true), null)
  const k = kb(real, { bang: 'yeu_cau', nhom: 'created_at' })
  assert.deepEqual(ketQua(k, [
    { created_at: '2026-10-31T17:30:00+00:00', count: 1 }, { created_at: '2026-11-02T01:00:00+00:00', count: 1 },
  ]), [{ nhan: '11/2026', giaTri: 2 }])
})

test('số, thanh, biểu đồ tròn', () => {
  assert.equal(so(1234.567, 'vi'), '1.234,57')
  assert.equal(so(1234.567, 'en'), '1,234.57')
  assert.equal(so(null, 'vi'), '—')
  assert.deepEqual(thanh([{ giaTri: 5 }, { giaTri: 10 }, { giaTri: -1 }, { giaTri: null }]), [50, 100, 0, 0])
  assert.deepEqual(thanh([{ giaTri: 0 }]), [0])

  const b = banhTron([{ nhan: 'a', giaTri: 1 }, { nhan: 'b', giaTri: 0 }, { nhan: 'c', giaTri: 3 }])
  assert.equal(b.nen, `conic-gradient(${MAU[0]} 0% 25%, ${MAU[1]} 25% 100%)`)
  assert.deepEqual(b.lat.map((x) => [x.nhan, x.mau]), [['a', MAU[0]], ['c', MAU[1]]])
  for (const bad of [[{ giaTri: 0 }], [{ giaTri: 2 }, { giaTri: -1 }], [{ giaTri: null }], []]) {
    assert.equal(banhTron(bad), null)
  }
  // từ lát thứ chín gộp vào "Khác": tám màu theo thứ tự, không quay vòng
  setLocale('vi')
  const many = banhTron(Array.from({ length: 10 }, (_, i) => ({ nhan: `n${i}`, giaTri: 1 })))
  assert.equal(many.lat.length, 8)
  assert.deepEqual(many.lat.at(-1), { nhan: 'Khác', giaTri: 3, mau: MAU[7] })
  assert.match(many.nen, / 100%\)$/)
})
