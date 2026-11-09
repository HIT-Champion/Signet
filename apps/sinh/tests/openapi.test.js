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
import {
  checkSchema, clean, fields, formErrors, localTime, message, mountForm, summary,
} from '../public/schema-form.js'

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
      // text là ô nhiều dòng (#303)
      tieu_de: { type: 'string', 'x-moc-ui': { widget: 'textarea', label: 'Tiêu đề' } },
      noi_dung: { type: ['string', 'null'], 'x-moc-ui': { widget: 'textarea' } },
      // cột có CHECK không có enum trong mô tả: ô chữ, CSDL từ chối giá trị ngoài CHECK (400)
      muc_uu_tien: { type: 'string', 'x-moc-ui': { widget: 'textarea', label: 'Mức ưu tiên' } },
      trang_thai: { type: 'string', enum: ['mới', 'đang xử lý', 'xong'], 'x-moc-ui': { label: 'Trạng thái' } },
      han: { type: ['string', 'null'], format: 'date', 'x-moc-ui': { label: 'Hạn xử lý' } },
    },
    'x-moc-order': ['tieu_de', 'noi_dung', 'muc_uu_tien', 'trang_thai', 'han'],
    required: ['tieu_de'],
  })
  assert.doesNotThrow(() => checkSchema(schema))
})

test('chú thích: bỏ phần Note PostgREST nối vào; dòng đầu là nhãn, dòng "en: " là nhãn tiếng Anh, còn lại là gợi ý',
  () => {
    assert.deepEqual(note('Note:\nThis is a Primary Key.<pk/>'), { label: '', en: '', help: '' })
    const fk = "Phòng phụ trách\n\nNote:\nThis is a Foreign Key to `phong.id`.<fk table='phong' column='id'/>"
    assert.deepEqual(note(fk), { label: 'Phòng phụ trách', en: '', help: '' })
    assert.deepEqual(note('Nội dung\nMô tả điều cần giải quyết.'),
      { label: 'Nội dung', en: '', help: 'Mô tả điều cần giải quyết.' })
    // chữ "Note:" giữa câu của người viết không bị cắt
    assert.deepEqual(note('Ghi chú (Note: tùy chọn)'), { label: 'Ghi chú (Note: tùy chọn)', en: '', help: '' })
    for (const v of [undefined, null, '']) assert.deepEqual(note(v), { label: '', en: '', help: '' })
    // dòng en ở đâu cũng được, chỉ dòng đầu tiên; "en:" giữa câu không tính
    assert.deepEqual(note('Nội dung\nGhi rõ sự việc.\nen: Content\nen: Thừa\nXem thêm en: mục 2'),
      { label: 'Nội dung', en: 'Content', help: 'Ghi rõ sự việc.\nen: Thừa\nXem thêm en: mục 2' })
    const fkEn = "Phòng\nen: Department\n\nNote:\nThis is a Foreign Key to `phong.id`.<fk table='phong' column='id'/>"
    assert.deepEqual(note(fkEn), { label: 'Phòng', en: 'Department', help: '' })
  })

test('menu: bảng có COMMENT ON TABLE (ở definitions hay paths), xếp theo tên; bảng không chú thích thì không', () => {
  assert.deepEqual(apps(spec()), [
    { table: 'phong', title: 'Danh mục phòng', help: '' },
    { table: 'yeu_cau', title: 'Quản lý yêu cầu', help: 'Gửi yêu cầu tới phòng phụ trách và theo dõi tới khi xong.' },
  ])
  for (const v of [null, undefined, {}, { definitions: null }]) assert.deepEqual(apps(v), [])
})

test('schema của bảng: bỏ cột chuẩn, khóa chính; bắt buộc, để trống, định dạng, nhãn, ô theo kiểu cột', () => {
  const { schema, key } = formSchema(spec(), 'yeu_cau')
  assert.equal(key, 'id')
  assert.equal(schema.title, 'Quản lý yêu cầu')
  assert.deepEqual(schema['x-moc-order'],
    ['tieu_de', 'noi_dung', 'han', 'trang_thai', 'so_luong', 'phong_id', 'dinh_kem', 'nhan'])
  for (const name of [...STANDARD, 'id']) assert.ok(!(name in schema.properties), name)
  // NOT NULL không mặc định là bắt buộc; NOT NULL có mặc định (trang_thai) để CSDL điền, không gửi null
  assert.deepEqual(schema.required, ['tieu_de'])
  assert.deepEqual(schema.properties.tieu_de,
    { type: 'string', maxLength: 200, 'x-moc-ui': { label: 'Tiêu đề' } })
  // text: ô nhiều dòng; varchar(n) (tieu_de) vẫn một dòng
  assert.deepEqual(schema.properties.noi_dung, { type: ['string', 'null'],
    'x-moc-ui': { widget: 'textarea', label: 'Nội dung', help: 'Mô tả điều cần giải quyết.' } })
  // jsonb: JSON bất kỳ, ô nhiều dòng kiểm JSON; mảng không phải enum: chỉ đọc
  assert.deepEqual(schema.properties.dinh_kem, { type: ['object', 'array', 'string', 'number', 'boolean', 'null'],
    'x-moc-ui': { widget: 'json', label: 'Tệp kèm' } })
  assert.deepEqual(schema.properties.nhan, { type: ['array', 'null'], 'x-moc-ui': { widget: 'readonly' } })
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
    ['tieu_de', 'text', 'Tiêu đề'], ['noi_dung', 'textarea', 'Nội dung'], ['han', 'date', 'Hạn giải quyết'],
    ['trang_thai', 'select', 'Trạng thái'], ['so_luong', 'number', 'so_luong'], ['phong_id', 'text', 'Phòng phụ trách'],
    ['dinh_kem', 'json', 'Tệp kèm'], ['nhan', 'readonly', 'nhan'],
  ])
  // bảng không có khóa chính: dựng được form thêm, không sửa được
  assert.equal(formSchema(spec(), 'phong').key, 'id')
  const noKey = spec()
  delete noKey.definitions.phong.properties.id
  assert.equal(formSchema(noKey, 'phong').key, null)
  // khóa ghép: các cột của khóa có ô (người dùng nhập), không sửa được vì PATCH chỉ lọc theo một cột
  const pair = spec()
  pair.definitions.phong.properties.ma = { description: 'Mã phòng\n\nNote:\nThis is a Primary Key.<pk/>',
    format: 'text', type: 'string' }
  const composite = formSchema(pair, 'phong')
  assert.equal(composite.key, null)
  assert.deepEqual(composite.schema['x-moc-order'], ['id', 'ten', 'ma'])
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
  // không gửi; không bao giờ có cột chuẩn, khóa chính hay ô chỉ đọc
  assert.deepEqual(handle.values(),
    { tieu_de: 'Máy in tầng 3 hỏng', noi_dung: null, han: null, so_luong: null, phong_id: null, dinh_kem: null })
  // danh sách: nhãn theo chú thích, giá trị đổi ra chữ
  const row = { id: 'x', tieu_de: 'Máy in tầng 3 hỏng', han: '2026-11-05', muc_uu_tien: 'Gấp', tenant_id: 't' }
  assert.deepEqual(summary(schema, row).map((r) => [r.label, r.value]).filter(([, v]) => v !== '—'),
    [['Tiêu đề', 'Máy in tầng 3 hỏng'], ['Hạn giải quyết', '05/11/2026'], ['Mức ưu tiên', 'Gấp']])
})

// cột thêm trong Studio cho các ca của #303 (PostgREST ghi format là tên kiểu PostgreSQL, mảng thêm "[]")
function moreColumns() {
  const s = spec()
  Object.assign(s.definitions.yeu_cau.properties, {
    hen_luc: { description: 'Hẹn lúc\nen: Appointment', format: 'timestamp with time zone', type: 'string' },
    gio_ghi: { format: 'timestamp without time zone', type: 'string' },
    // PostgREST không ghi enum cho cột mảng: lấy từ cột trang_thai cùng kiểu
    buoc: { description: 'Các bước đã qua', format: 'sinh.trang_thai_yeu_cau[]', items: { type: 'string' },
      type: 'array' },
    ma_so: { format: 'integer[]', items: { type: 'integer' }, type: 'array' },
  })
  s.definitions.yeu_cau.required = [...(s.definitions.yeu_cau.required ?? []), 'ma_so']
  return s
}

test('ô theo kiểu cột: ngày giờ, mảng enum nhiều ô đánh dấu, mảng khác chỉ đọc và không bắt buộc', () => {
  const { schema } = formSchema(moreColumns(), 'yeu_cau')
  const p = schema.properties
  assert.deepEqual(p.hen_luc,
    { type: ['string', 'null'], 'x-moc-ui': { widget: 'datetime', label: { vi: 'Hẹn lúc', en: 'Appointment' } } })
  assert.deepEqual(p.gio_ghi, { type: ['string', 'null'], 'x-moc-ui': { widget: 'datetime' } })
  assert.deepEqual(p.buoc, { type: ['array', 'null'], items: { type: 'string', enum: ['Mới', 'Đang xử lý', 'Xong'] },
    'x-moc-ui': { label: 'Các bước đã qua' } })
  // NOT NULL không mặc định nhưng chỉ đọc: không bắt buộc (người dùng không điền được)
  assert.deepEqual(p.ma_so, { type: 'array', 'x-moc-ui': { widget: 'readonly' } })
  assert.ok(!schema.required.includes('ma_so'))
  assert.doesNotThrow(() => checkSchema(schema))
  const by = Object.fromEntries(fields(schema, 'en').map((f) => [f.name, f]))
  assert.equal(by.hen_luc.widget, 'datetime')
  assert.equal(by.hen_luc.label, 'Appointment')
  assert.equal(by.buoc.widget, 'checkboxes')
  assert.deepEqual(by.buoc.options.map((o) => o.value), ['Mới', 'Đang xử lý', 'Xong'])
  // items.enum ghi sẵn (bản PostgREST sau này) thì dùng luôn
  const own = moreColumns()
  own.definitions.yeu_cau.properties.ma_so = { format: 'text[]', items: { type: 'string', enum: ['a', 'b'] },
    type: 'array' }
  assert.deepEqual(formSchema(own, 'yeu_cau').schema.properties.ma_so.items, { type: 'string', enum: ['a', 'b'] })
  // mảng enum đánh dấu được; ô đánh dấu sai giá trị thì bộ kiểm báo enum
  assert.deepEqual(formErrors(schema, { tieu_de: 'A', buoc: ['Xong', 'Lạ'] }), { buoc: 'enum' })
})

test('nhãn hai thứ tiếng: dòng "en: " của COMMENT ON COLUMN và COMMENT ON TABLE', () => {
  const s = spec()
  s.definitions.yeu_cau.description = 'Quản lý yêu cầu\nen: Requests\nGửi yêu cầu tới phòng phụ trách.'
  s.definitions.yeu_cau.properties.tieu_de.description = 'Tiêu đề\nen: Title\nNgắn gọn, dưới 200 ký tự.'
  assert.deepEqual(apps(s, 'en').map((a) => [a.table, a.title, a.help]),
    [['phong', 'Danh mục phòng', ''], ['yeu_cau', 'Requests', 'Gửi yêu cầu tới phòng phụ trách.']])
  assert.equal(apps(s, 'vi').find((a) => a.table === 'yeu_cau').title, 'Quản lý yêu cầu')
  const { schema } = formSchema(s, 'yeu_cau')
  assert.deepEqual(schema['x-moc-title'], { vi: 'Quản lý yêu cầu', en: 'Requests' })
  assert.deepEqual(schema.properties.tieu_de['x-moc-ui'],
    { label: { vi: 'Tiêu đề', en: 'Title' }, help: 'Ngắn gọn, dưới 200 ký tự.' })
  const doc = fakeDocument()
  const box = doc.createElement('div')
  mountForm(box, schema, { lang: 'en', idPrefix: 'moi-' })
  assert.equal(box.children[0].attrs['aria-label'], 'Requests')
  assert.ok(labels(box).includes('Title'))
  mountForm(box, schema, { lang: 'vi', idPrefix: 'moi-' })
  assert.ok(labels(box).includes('Tiêu đề'))
})

test('ô json: đọc JSON khi gửi, gõ chưa đúng thì báo và giữ chữ khi form dựng lại', async () => {
  const { schema } = formSchema(spec(), 'yeu_cau')
  const list = fields(schema)
  assert.deepEqual(clean(list, { tieu_de: 'A', dinh_kem: ' {"tep": ["a.pdf"]} ' }).dinh_kem, { tep: ['a.pdf'] })
  const bad = clean(list, { tieu_de: 'A', dinh_kem: '{"tep": ' })
  assert.deepEqual(formErrors(schema, bad), { dinh_kem: 'x-moc-json' })
  const f = list.find((x) => x.name === 'dinh_kem')
  assert.equal(message(f, 'x-moc-json', 'vi'), 'Chưa đúng cú pháp JSON')
  assert.equal(message(f, 'x-moc-json', 'en'), 'Not valid JSON')
  // chuỗi JSON hợp lệ vẫn là giá trị đúng của cột json
  assert.equal(clean(list, { tieu_de: 'A', dinh_kem: '"abc"' }).dinh_kem, 'abc')

  const doc = fakeDocument()
  const box = doc.createElement('div')
  const sent = []
  const handle = mountForm(box, schema, { idPrefix: 'sua-', values: { tieu_de: 'A', dinh_kem: { a: 1 } },
    onSubmit: (data) => sent.push(data) })
  const area = nodes(box).find((n) => n.id === 'sua-dinh_kem')
  assert.equal(area.tag, 'textarea')
  assert.equal(area.value, '{\n  "a": 1\n}')
  area.value = '{"a": '
  await box.children[0].on.submit({ preventDefault() {} })
  assert.deepEqual(sent, [])
  assert.equal(text(nodes(box).find((n) => n.id === 'sua-dinh_kem-error')), 'Chưa đúng cú pháp JSON')
  // trang dựng lại form (đổi ngôn ngữ, quay lại tab): chữ gõ dở còn nguyên
  mountForm(box, schema, { idPrefix: 'sua-', draft: handle.values() })
  assert.equal(nodes(box).find((n) => n.id === 'sua-dinh_kem').value, '{"a": ')
  assert.equal(summary(schema, { dinh_kem: [1, { b: 2 }] }).find((r) => r.name === 'dinh_kem').value, '[1,{"b":2}]')
})

test('ô ngày giờ gửi kèm độ lệch múi giờ của máy; ô chỉ đọc hiện giá trị, không gửi', () => {
  const { schema } = formSchema(moreColumns(), 'yeu_cau')
  const list = fields(schema)
  const sent = clean(list, { tieu_de: 'A', hen_luc: '2026-11-10T08:30', ma_so: [1, 2] })
  // cùng thời điểm với giờ đã gõ theo giờ của máy, chạy ở múi giờ nào cũng đúng
  assert.match(sent.hen_luc, /^2026-11-10T08:30:00[+-]\d{2}:\d{2}$/)
  assert.equal(new Date(sent.hen_luc).getTime(), new Date('2026-11-10T08:30').getTime())
  assert.ok(!('ma_so' in sent))
  assert.equal(localTime(sent.hen_luc), '2026-11-10T08:30')
  // timestamp không múi giờ đọc về giữ nguyên giờ; timestamptz đổi sang giờ của máy; 6 chữ số phần giây vẫn đọc được
  assert.equal(localTime('2026-11-10T08:30:00'), '2026-11-10T08:30')
  const instant = new Date('2026-11-10T01:30:00.123Z')
  assert.equal(localTime('2026-11-10T01:30:00.123456+00:00'), localTime(instant.toISOString()))
  assert.equal(new Date(localTime('2026-11-10T01:30:00.123456+00:00')).getTime(), instant.getTime() - 123)
  for (const v of ['', 'x', null, 5]) assert.equal(localTime(v), '')

  const doc = fakeDocument()
  const box = doc.createElement('div')
  const handle = mountForm(box, schema, { idPrefix: 'sua-',
    values: { tieu_de: 'A', hen_luc: '2026-11-10T08:30:00', ma_so: [1, 2] } })
  const when = nodes(box).find((n) => n.id === 'sua-hen_luc')
  assert.deepEqual([when.type, when.value], ['datetime-local', '2026-11-10T08:30'])
  const only = nodes(box).find((n) => n.id === 'sua-ma_so')
  assert.deepEqual([only.readOnly, only.value, only.required], [true, '1, 2', false])
  // ô chỉ đọc không ghi "(không bắt buộc)"
  assert.ok(labels(box).includes('ma_so'))
  assert.ok(!('ma_so' in handle.values()))
  assert.equal(summary(schema, { hen_luc: '2026-11-10T08:30:00' }).find((r) => r.name === 'hen_luc').value,
    '10/11/2026 08:30')
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
  // truy vấn gộp của báo cáo (#587) không xin đếm
  assert.equal(yeuCau('tok', 'GET', '/yeu_cau?select=trang_thai,count()')[1].headers.Prefer, undefined)
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
