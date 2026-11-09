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
// json, jsonb: PostgREST không ghi type; giá trị là JSON bất kỳ
const ANY_JSON = ['object', 'array', 'string', 'number', 'boolean']
// ô theo kiểu cột (#303): schema-form.js chỉ vẽ các ô này khi x-moc-ui.widget ghi rõ
const WIDGET = {
  text: 'textarea',
  'timestamp with time zone': 'datetime',
  'timestamp without time zone': 'datetime',
  json: 'json',
  jsonb: 'json',
}

/**
 * Chú thích (COMMENT) của bảng hay cột, bỏ phần "Note: … <pk/> <fk …/>" PostgREST nối vào. Dòng đầu là nhãn tiếng
 * Việt, một dòng "en: …" là nhãn tiếng Anh (rỗng nếu không có), các dòng còn lại là gợi ý.
 */
export function note(description) {
  const text = String(description ?? '').replace(/(?:^|\n\n)Note:\n[\s\S]*$/, '').replace(/<(?:pk|fk)\b[^>]*\/>/g, '')
  const [first = '', ...rest] = text.trim().split('\n')
  const en = rest.find((line) => /^en:/.test(line.trim()))
  return {
    label: first.trim(),
    en: en === undefined ? '' : en.trim().slice(3).trim(),
    help: rest.filter((line) => line !== en).join('\n').trim(),
  }
}

// nhãn hai thứ tiếng cho schema-form.js ({vi, en}); không có dòng en thì chuỗi như cũ
const bilingual = ({ label, en }) => (en ? { vi: label, en } : label)

// Giá trị enum của phần tử mảng. PostgREST chỉ ghi items.type cho cột mảng, không ghi enum (pg_enum tra theo kiểu
// mảng): lấy từ cột thường có cùng kiểu enum ở bảng bất kỳ. Không thấy thì null, cột thành ô chỉ đọc
function arrayEnum(spec, p) {
  if (Array.isArray(p.items?.enum) && p.items.enum.length) return [...p.items.enum]
  const type = typeof p.format === 'string' && p.format.endsWith('[]') ? p.format.slice(0, -2) : ''
  for (const def of Object.values(spec.definitions)) {
    for (const q of Object.values(def?.properties ?? {})) {
      if (type && q?.format === type && Array.isArray(q.enum) && q.enum.length) return [...q.enum]
    }
  }
  return null
}

const isKey = (prop) => /<pk\/>/.test(String(prop?.description ?? ''))

// PostgREST v14 ghi COMMENT ON TABLE ở definitions.<bảng>.description, và tách đôi ở paths./<bảng>.get: dòng đầu là
// summary, phần sau là description
function tableNote(spec, table) {
  const get = spec?.paths?.[`/${table}`]?.get
  return spec.definitions[table]?.description || [get?.summary, get?.description].filter(Boolean).join('\n')
}

/**
 * Các ứng dụng: bảng có COMMENT ON TABLE, xếp theo tên. Bảng không chú thích là bảng phụ, không lên menu. Tên theo
 * lang: tiếng Anh là dòng "en: …" của chú thích, không có thì tên tiếng Việt.
 */
export function apps(spec, lang = 'vi') {
  return Object.keys(spec?.definitions ?? {})
    .map((table) => ({ table, ...note(tableNote(spec, table)) }))
    .filter((a) => a.label)
    .map(({ table, label, en, help }) => ({ table, title: (lang === 'en' && en) || label, help }))
    .sort((a, b) => a.title.localeCompare(b.title, lang))
}

/**
 * Schema cho schema-form.js từ definitions.<bảng>: { schema, key } (key: tên cột khóa chính để sửa bằng PATCH, null
 * nếu không có). Không có bảng thì null.
 *  - Bỏ cột chuẩn, khóa chính một cột, cột kiểu lạ.
 *  - Ô theo kiểu cột: text nhiều dòng, timestamp/timestamptz chọn ngày giờ, json/jsonb nhiều dòng kiểm JSON, mảng
 *    enum nhiều ô đánh dấu, mảng khác chỉ đọc (không bắt buộc, không gửi).
 *  - Khóa chính nhiều cột: các cột đó là dữ liệu người dùng nhập nên vẫn có ô; key null, tức là không sửa được.
 *  - Bắt buộc: NOT NULL mà không có giá trị mặc định. Có mặc định thì để trống, CSDL tự điền.
 *  - Được để trống (gửi null): cột không bắt buộc, không có mặc định.
 *  - Nhãn, tên form hai thứ tiếng khi chú thích có dòng "en: …".
 */
export function formSchema(spec, table) {
  const def = spec?.definitions?.[table]
  if (!def) return null
  const props = def.properties ?? {}
  const listed = new Set(def.required ?? [])
  const keys = Object.keys(props).filter((name) => isKey(props[name]))
  // shortcut: PATCH lọc theo một cột, nên khóa ghép thì không sửa; cần thì lọc theo đủ các cột của khóa
  const key = keys.length === 1 ? keys[0] : null
  const properties = {}
  const required = []
  for (const [name, p] of Object.entries(props)) {
    if (STANDARD.has(name) || name === key) continue
    const json = p?.format === 'json' || p?.format === 'jsonb'
    const array = p?.type === 'array'
    if (!json && !array && !TYPES.has(p?.type)) continue
    const choices = array ? arrayEnum(spec, p) : null
    const readonly = array && !choices
    const hasDefault = Object.hasOwn(p, 'default')
    // shortcut: ô chọn không bắt buộc không có null trong enum (sẽ thành một lựa chọn "null"), nên sửa không xóa về
    // trống được; cần thì thêm x-moc-ui.options cho null
    const nullable = !listed.has(name) && !hasDefault && !Array.isArray(p.enum)
    const type = json ? ANY_JSON : p.type
    const out = { type: nullable ? [type, 'null'].flat() : type }
    if (choices) out.items = { type: 'string', enum: choices }
    if (Array.isArray(p.enum) && p.enum.length) out.enum = [...p.enum]
    if (FORMATS.has(p.format)) out.format = p.format
    if (Number.isInteger(p.maxLength) && p.maxLength >= 0) out.maxLength = p.maxLength
    const text = note(p.description)
    const ui = {}
    const widget = readonly ? 'readonly' : out.enum ? undefined : WIDGET[p.format]
    if (widget) ui.widget = widget
    if (text.label) ui.label = bilingual(text)
    if (text.help) ui.help = text.help
    if (Object.keys(ui).length) out['x-moc-ui'] = ui
    properties[name] = out
    if (listed.has(name) && !hasDefault && !readonly) required.push(name)
  }
  const title = note(def.description)
  const schema = { type: 'object', title: title.label || table, properties, 'x-moc-order': Object.keys(properties) }
  if (title.en) schema['x-moc-title'] = bilingual(title)
  if (required.length) schema.required = required
  return { schema, key }
}
