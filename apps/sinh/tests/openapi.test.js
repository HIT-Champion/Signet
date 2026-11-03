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

// #560: mô tả API PostgREST sinh (GET /rest/v1/) → menu và JSON Schema cho schema-form.js, và cách gọi /rest/v1.
// Hai tệp mô tả: postgrest-v14-openapi.json lấy thật từ PostgREST v14.18 trong bộ thử trên CI (run 41691183259,
// bảng mẫu sinh.yeu_cau); postgrest-openapi.json viết tay theo đúng dạng đó để có các ca bản thật chưa có (khóa
// ngoại, json, mảng, bảng không chú thích, chú thích nhiều dòng).

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

import { STANDARD, apps, formSchema, note } from '../public/openapi.js'
import { API, PAGE, docThan, duong, tongSo, yeuCau } from '../public/rest.js'
import { checkSchema, fields, mountForm, summary } from '../public/schema-form.js'

const read = (name) => JSON.parse(readFileSync(new URL(name, import.meta.url), 'utf8'))
const spec = () => read('postgrest-openapi.json')

test('mô tả thật của PostgREST v14: menu, schema của bảng mẫu sinh.yeu_cau', () => {
  const real = read('postgrest-v14-openapi.json')
  assert.deepEqual(apps(real), [{ table: 'yeu_cau', title: 'Quản lý yêu cầu', help: '' }])
  const { schema, key } = formSchema(real, 'yeu_cau')
  assert.equal(key, 'id')
  // required của PostgREST có mọi cột NOT NULL: bỏ cột chuẩn, khóa chính, cột có mặc định (trang_thai, muc_uu_tien)
  assert.deepEqual(schema, {
    type: 'object',
    title: 'Quản lý yêu cầu',
    properties: {
      tieu_de: { type: 'string', 'x-moc-ui': { label: 'Tiêu đề' } },
      noi_dung: { type: ['string', 'null'] },
      // cột có CHECK không có enum trong mô tả: ô chữ, CSDL từ chối giá trị ngoài CHECK (400)
      muc_uu_tien: { type: 'string', 'x-moc-ui': { label: 'Mức ưu tiên' } },
      trang_thai: { type: 'string', enum: ['mới', 'đang xử lý', 'xong'], 'x-moc-ui': { label: 'Trạng thái' } },
      han: { type: ['string', 'null'], format: 'date', 'x-moc-ui': { label: 'Hạn xử lý' } },
    },
    'x-moc-order': ['tieu_de', 'noi_dung', 'muc_uu_tien', 'trang_thai', 'han'],
    required: ['tieu_de'],
  })
  assert.doesNotThrow(() => checkSchema(schema))
})

test('chú thích: bỏ phần Note PostgREST nối vào; dòng đầu là nhãn, các dòng sau là gợi ý', () => {
  assert.deepEqual(note('Note:\nThis is a Primary Key.<pk/>'), { label: '', help: '' })
  const fk = "Phòng phụ trách\n\nNote:\nThis is a Foreign Key to `phong.id`.<fk table='phong' column='id'/>"
  assert.deepEqual(note(fk), { label: 'Phòng phụ trách', help: '' })
  assert.deepEqual(note('Nội dung\nMô tả điều cần giải quyết.'),
    { label: 'Nội dung', help: 'Mô tả điều cần giải quyết.' })
  // chữ "Note:" giữa câu của người viết không bị cắt
  assert.deepEqual(note('Ghi chú (Note: tùy chọn)'), { label: 'Ghi chú (Note: tùy chọn)', help: '' })
  for (const v of [undefined, null, '']) assert.deepEqual(note(v), { label: '', help: '' })
})

test('menu: bảng có COMMENT ON TABLE (ở definitions hay paths), xếp theo tên; bảng không chú thích thì không', () => {
  assert.deepEqual(apps(spec()), [
    { table: 'phong', title: 'Danh mục phòng', help: '' },
    { table: 'yeu_cau', title: 'Quản lý yêu cầu', help: 'Gửi yêu cầu tới phòng phụ trách và theo dõi tới khi xong.' },
  ])
  for (const v of [null, undefined, {}, { definitions: null }]) assert.deepEqual(apps(v), [])
})

test('schema của bảng: bỏ cột chuẩn, khóa chính, cột json và mảng; bắt buộc, để trống, định dạng, nhãn', () => {
  const { schema, key } = formSchema(spec(), 'yeu_cau')
  assert.equal(key, 'id')
  assert.equal(schema.title, 'Quản lý yêu cầu')
  assert.deepEqual(schema['x-moc-order'], ['tieu_de', 'noi_dung', 'han', 'trang_thai', 'so_luong', 'phong_id'])
  for (const name of [...STANDARD, 'id', 'dinh_kem', 'nhan']) assert.ok(!(name in schema.properties), name)
  // NOT NULL không mặc định là bắt buộc; NOT NULL có mặc định (trang_thai) để CSDL điền, không gửi null
  assert.deepEqual(schema.required, ['tieu_de'])
  assert.deepEqual(schema.properties.tieu_de,
    { type: 'string', maxLength: 200, 'x-moc-ui': { label: 'Tiêu đề' } })
  // text là kiểu Studio đặt sẵn cho mọi cột chữ, không nói gì về độ dài: ô một dòng như varchar
  assert.deepEqual(schema.properties.noi_dung,
    { type: ['string', 'null'], 'x-moc-ui': { label: 'Nội dung', help: 'Mô tả điều cần giải quyết.' } })
  assert.deepEqual(schema.properties.han,
    { type: ['string', 'null'], format: 'date', 'x-moc-ui': { label: 'Hạn giải quyết' } })
  assert.deepEqual(schema.properties.trang_thai,
    { type: 'string', enum: ['Mới', 'Đang xử lý', 'Xong'], 'x-moc-ui': { label: 'Trạng thái' } })
  // cột không chú thích: không có x-moc-ui, schema-form.js lấy tên cột làm nhãn
  assert.deepEqual(schema.properties.so_luong, { type: ['integer', 'null'] })
  assert.deepEqual(schema.properties.phong_id,
    { type: ['string', 'null'], format: 'uuid', 'x-moc-ui': { label: 'Phòng phụ trách' } })
  // schema-form.js nhận schema này: không còn format lạ (character varying, timestamp…), x-moc-order đủ trường
  assert.doesNotThrow(() => checkSchema(schema))
  assert.deepEqual(fields(schema).map((f) => [f.name, f.widget, f.label]), [
    ['tieu_de', 'text', 'Tiêu đề'], ['noi_dung', 'text', 'Nội dung'], ['han', 'date', 'Hạn giải quyết'],
    ['trang_thai', 'select', 'Trạng thái'], ['so_luong', 'number', 'so_luong'], ['phong_id', 'text', 'Phòng phụ trách'],
  ])
  // bảng không có khóa chính: dựng được form thêm, không sửa được
  assert.equal(formSchema(spec(), 'phong').key, 'id')
  const noKey = spec()
  delete noKey.definitions.phong.properties.id
  assert.equal(formSchema(noKey, 'phong').key, null)
  assert.equal(formSchema(spec(), 'khong_co'), null)
  assert.equal(formSchema(null, 'yeu_cau'), null)
})

// DOM giả vừa đủ cho mountForm (chép từ apps/nghi-phep/tests/i18n.test.js): phần tử là đối tượng thường
function fakeDocument() {
  const doc = {
    focused: null,
    createElement: (tag) => ({
      tag, children: [], attrs: {}, on: {}, textContent: '', ownerDocument: doc,
      append(...nodes) { this.children.push(...nodes) },
      prepend(...nodes) { this.children.unshift(...nodes) },
      replaceChildren(...nodes) { this.children = nodes },
      setAttribute(name, value) { this.attrs[name] = String(value) },
      removeAttribute(name) { delete this.attrs[name] },
      addEventListener(type, fn) { this.on[type] = fn },
      focus() { doc.focused = this },
    }),
  }
  return doc
}
const text = (node) => (typeof node === 'string' ? node : node.textContent + node.children.map(text).join(''))
const nodes = (node) => (typeof node === 'string' ? [] : [node, ...node.children.flatMap(nodes)])
const labels = (box) => nodes(box).filter((n) => n.className === 'sf-label').map(text)

test('thêm cột "Mức ưu tiên" trong Studio: form dựng lại có ô chọn mới, không sửa mã', () => {
  const doc = fakeDocument()
  const box = doc.createElement('div')
  const before = formSchema(spec(), 'yeu_cau').schema
  mountForm(box, before, { idPrefix: 'moi-' })
  assert.ok(!labels(box).some((l) => l.startsWith('Mức ưu tiên')))

  // kiểu enum + COMMENT ON COLUMN tạo trong Studio; PostgREST nạp lại lược đồ sau NOTIFY pgrst của khung CSDL
  const after = spec()
  after.definitions.yeu_cau.properties.muc_uu_tien = {
    description: 'Mức ưu tiên', enum: ['Thấp', 'Thường', 'Gấp'], format: 'sinh.muc_uu_tien', type: 'string',
  }
  const { schema } = formSchema(after, 'yeu_cau')
  const handle = mountForm(box, schema, { idPrefix: 'moi-', draft: { tieu_de: 'Máy in tầng 3 hỏng' } })
  assert.ok(labels(box).includes('Mức ưu tiên (không bắt buộc)'))
  const select = nodes(box).find((n) => n.id === 'moi-muc_uu_tien')
  assert.deepEqual(select.children.map(text), ['— Chọn —', 'Thấp', 'Thường', 'Gấp'])
  // dữ liệu gửi đi: chữ đang gõ giữ nguyên; ô để trống được thì gửi null; ô chọn để trống và cột có mặc định thì
  // không gửi; không bao giờ có cột chuẩn hay khóa chính
  assert.deepEqual(handle.values(),
    { tieu_de: 'Máy in tầng 3 hỏng', noi_dung: null, han: null, so_luong: null, phong_id: null })
  // danh sách: nhãn theo chú thích, giá trị đổi ra chữ
  const row = { id: 'x', tieu_de: 'Máy in tầng 3 hỏng', han: '2026-11-05', muc_uu_tien: 'Gấp', tenant_id: 't' }
  assert.deepEqual(summary(schema, row).map((r) => [r.label, r.value]).filter(([, v]) => v !== '—'),
    [['Tiêu đề', 'Máy in tầng 3 hỏng'], ['Hạn giải quyết', '05/11/2026'], ['Mức ưu tiên', 'Gấp']])
})

test('schema-form.js là bản chép từng byte của apps/nghi-phep', () => {
  const read = (path) => readFileSync(new URL(path, import.meta.url), 'utf8')
  assert.equal(read('../public/schema-form.js'), read('../../nghi-phep/public/schema-form.js'),
    'sửa apps/nghi-phep/public/schema-form.js thì chép lại sang apps/sinh/public/')
})

test('gọi /rest/v1: địa chỉ, token, Prefer; tổng số dòng; thân không phải JSON', () => {
  assert.equal(API, '/rest/v1')
  assert.equal(duong.spec(), '/')
  assert.equal(duong.rows('yeu_cau'), `/yeu_cau?order=created_at.desc&limit=${PAGE}`)
  assert.equal(duong.create('yeu_cau'), '/yeu_cau')
  // giá trị khóa đi vào chuỗi truy vấn: mã hóa, không chèn được toán tử hay tham số khác
  assert.equal(duong.row('yeu_cau', 'id', 'a&b=eq.1'), '/yeu_cau?id=eq.a%26b%3Deq.1')
  assert.equal(duong.rows('bảng?x'), `/b%E1%BA%A3ng%3Fx?order=created_at.desc&limit=${PAGE}`)

  const [url, init] = yeuCau('tok', 'GET', duong.spec())
  assert.equal(url, '/rest/v1/')
  assert.deepEqual(init, { method: 'GET', cache: 'no-store',
    headers: { Authorization: 'Bearer tok', Accept: 'application/json' } })
  assert.equal(yeuCau('tok', 'GET', duong.rows('yeu_cau'))[1].headers.Prefer, 'count=exact')
  const [, post] = yeuCau('tok', 'POST', duong.create('yeu_cau'), { tieu_de: 'A' })
  assert.deepEqual([post.headers.Prefer, post.headers['Content-Type'], post.body],
    ['return=representation', 'application/json', '{"tieu_de":"A"}'])
  assert.equal(yeuCau('tok', 'PATCH', duong.row('yeu_cau', 'id', '1'), { han: null })[1].body, '{"han":null}')

  assert.equal(tongSo('0-49/120'), 120)
  assert.equal(tongSo('*/0'), 0)
  for (const v of ['0-49/*', '', null, undefined]) assert.equal(tongSo(v), null)
  assert.deepEqual(docThan('[{"id":1}]'), [{ id: 1 }])
  for (const v of ['', null, '<html>403 Forbidden</html>']) assert.equal(docThan(v), null)
})
