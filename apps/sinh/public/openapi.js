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

// Đổi mô tả API mà PostgREST tự sinh (GET /rest/v1/, Swagger 2.0) ra JSON Schema cho schema-form.js (#560). Bảng
// tạo trong Studio ở schema sinh thành một ứng dụng: COMMENT ON TABLE là tên, COMMENT ON COLUMN là nhãn ô. Thêm cột
// thì ô nhập hiện ngay, không sửa mã. Hàm thuần, không đụng trình duyệt: test bằng node --test.

// Cột khung CSDL tự thêm vào mọi bảng; người gọi không ghi được nên không có ô
export const STANDARD = new Set(['tenant_id', 'created_by', 'created_at'])
// schema-form.js báo lỗi lúc nạp với định dạng khác hai cái này; PostgREST ghi tên kiểu PostgreSQL vào format
const FORMATS = new Set(['date', 'uuid'])
const TYPES = new Set(['string', 'integer', 'number', 'boolean'])

/** Chú thích (COMMENT) của bảng hay cột, bỏ phần "Note: … <pk/> <fk …/>" PostgREST nối vào. Dòng đầu, các dòng sau. */
export function note(description) {
  const text = String(description ?? '').replace(/(?:^|\n\n)Note:\n[\s\S]*$/, '').replace(/<(?:pk|fk)\b[^>]*\/>/g, '')
  const [first = '', ...rest] = text.trim().split('\n')
  return { label: first.trim(), help: rest.join('\n').trim() }
}

const isKey = (prop) => /<pk\/>/.test(String(prop?.description ?? ''))

/** Các ứng dụng: bảng có COMMENT ON TABLE, xếp theo tên. Bảng không chú thích là bảng phụ, không lên menu. Chú
 *  thích lấy ở definitions.<bảng>, không có thì ở paths./<bảng> (PostgREST ghi cả hai chỗ). */
export function apps(spec) {
  return Object.entries(spec?.definitions ?? {})
    .map(([table, def]) => ({ table, ...note(def?.description || spec?.paths?.[`/${table}`]?.description) }))
    .filter((a) => a.label)
    .map(({ table, label, help }) => ({ table, title: label, help }))
    .sort((a, b) => a.title.localeCompare(b.title, 'vi'))
}

/**
 * Schema cho schema-form.js từ definitions.<bảng>: { schema, key } (key: tên cột khóa chính để sửa bằng PATCH, null
 * nếu không có). Không có bảng thì null.
 *  - Bỏ cột chuẩn, khóa chính, cột json/mảng (form không có ô cho chúng).
 *  - Bắt buộc: NOT NULL mà không có giá trị mặc định. Có mặc định thì để trống, CSDL tự điền.
 *  - Được để trống (gửi null): cột không bắt buộc, không có mặc định.
 */
export function formSchema(spec, table) {
  const def = spec?.definitions?.[table]
  if (!def) return null
  const props = def.properties ?? {}
  const listed = new Set(def.required ?? [])
  const key = Object.keys(props).find((name) => isKey(props[name])) ?? null
  const properties = {}
  const required = []
  for (const [name, p] of Object.entries(props)) {
    if (STANDARD.has(name) || name === key || !TYPES.has(p?.type)) continue
    const hasDefault = Object.hasOwn(p, 'default')
    // shortcut: ô chọn không bắt buộc không có null trong enum (sẽ thành một lựa chọn "null"), nên sửa không xóa về
    // trống được; cần thì thêm x-moc-ui.options cho null
    const nullable = !listed.has(name) && !hasDefault && !Array.isArray(p.enum)
    const out = { type: nullable ? [p.type, 'null'] : p.type }
    if (Array.isArray(p.enum) && p.enum.length) out.enum = [...p.enum]
    if (FORMATS.has(p.format)) out.format = p.format
    if (Number.isInteger(p.maxLength) && p.maxLength >= 0) out.maxLength = p.maxLength
    const { label, help } = note(p.description)
    const ui = {}
    if (label) ui.label = label
    if (help) ui.help = help
    // text không giới hạn độ dài: ô nhiều dòng; varchar(n) giữ ô một dòng
    if (p.format === 'text' && !out.enum) ui.widget = 'textarea'
    if (Object.keys(ui).length) out['x-moc-ui'] = ui
    properties[name] = out
    if (listed.has(name) && !hasDefault) required.push(name)
  }
  const { label } = note(def.description)
  const schema = { type: 'object', title: label || table, properties, 'x-moc-order': Object.keys(properties) }
  if (required.length) schema.required = required
  return { schema, key }
}
