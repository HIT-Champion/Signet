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

// Bảng dịch vi/en của ứng dụng Bảng sinh (#560), cùng cách làm với apps/nghi-phep/public/i18n.js. Mọi chữ trên giao
// diện lấy từ đây: mã gọi t('khóa'), phần tĩnh của index.html mang data-i18n (tests/i18n.test.js kiểm cả hai). Câu
// chung của form dựng từ schema (form.*, schema.*) cũng ở đây. Tên bảng, nhãn ô lấy từ COMMENT trong CSDL (một thứ
// tiếng, người vận hành đặt trong Studio), không ở bảng này. Ngôn ngữ chọn lưu ở localStorage khóa `moc.locale`,
// chung với Văn phòng điện tử và các ứng dụng khác cùng tên miền. Không đụng DOM khi nạp nên chạy được dưới
// node --test.

export const STORAGE_KEY = 'moc.locale'

export const MESSAGES = Object.freeze({
  vi: Object.freeze({
    'page.title': 'Ứng dụng sinh từ bảng — Signet',
    'page.description': 'Signet — ứng dụng dựng tự động từ bảng mô tả trong Studio, API do PostgREST sinh',
    'page.skip': 'Bỏ qua, tới nội dung chính',
    'page.brand': 'Ứng dụng sinh từ bảng',
    'page.tagline': 'Signet · Studio + PostgREST',
    'page.footer': 'Trang này không viết riêng cho bảng nào: menu, danh sách và biểu mẫu dựng từ mô tả API mà '
      + 'PostgREST sinh từ các bảng trong schema sinh. Thêm cột trong Studio thì ô nhập hiện ở đây ngay.',
    'nav.apps': 'Ứng dụng',
    'nav.office': 'Văn phòng điện tử',
    'nav.logout': 'Đăng xuất',
    'nav.tables': 'Các ứng dụng sinh từ bảng',
    'lang.switch': 'English',
    'lang.other': 'en',
    'status.signingIn': 'Đang đăng nhập…',
    'status.signedIn': 'Đã đăng nhập',
    'status.loading': 'Đang nạp mô tả các bảng…',
    'status.redirecting': 'Đang chuyển sang trang đăng nhập…',
    'apps.empty': 'Chưa có bảng nào có chú thích (COMMENT ON TABLE) trong schema sinh.',
    'list.heading': 'Danh sách',
    'list.empty': 'Chưa có dòng nào.',
    'list.edit': 'Sửa',
    'list.createdAt': 'Tạo lúc {time}',
    'list.more': 'Hiện {shown}/{total} dòng mới nhất.',
    'create.heading': 'Thêm mới',
    'create.submit': 'Thêm',
    'edit.heading': 'Sửa dòng',
    'edit.submit': 'Lưu',
    'edit.cancel': 'Hủy',
    'notice.created': 'Đã thêm.',
    'notice.saved': 'Đã lưu.',
    // báo cáo động (#587, bao-cao.js): khai báo là một dòng của bảng bao_cao
    'report.view': 'Xem báo cáo',
    'report.close': 'Đóng báo cáo',
    'report.loading': 'Đang tính…',
    'report.failed': 'Không tính được báo cáo: {error}',
    'report.empty': 'Chưa có dòng nào để tính.',
    'report.blank': '(trống)',
    'report.other': 'Khác',
    'report.byMonth': '{column} (theo tháng)',
    'report.count': 'Số dòng',
    'report.sum': 'Tổng {column}',
    'report.avg': 'Trung bình {column}',
    'report.noTable': 'Không có bảng «{table}» trong schema sinh.',
    'report.noColumn': 'Bảng «{table}» không có cột «{column}».',
    'report.badGroup': 'Cột nhóm «{column}» phải là cột chọn từ danh sách (enum) hoặc cột ngày.',
    'report.badOp': 'Không có phép tính «{op}».',
    'report.needNumber': 'Tính tổng hay trung bình thì cần điền cột số.',
    'report.badNumber': 'Cột «{column}» không phải cột số.',
    'error.loadSpec': 'Không nạp được mô tả các bảng: {error}',
    'error.loadRows': 'Không tải được danh sách: {error}',
    'error.sendFailed': 'Chưa lưu được: {error}',
    'error.badForm': 'Bảng này chưa dựng được biểu mẫu: {error}',
    // câu theo mã trả lời của /rest/v1 (LOI trong rest.js)
    'error.network': 'Không gọi được Signet. Kiểm tra kết nối mạng rồi thử lại.',
    'error.session': 'Phiên đăng nhập đã hết. Tải lại trang để đăng nhập lại.',
    'error.forbidden': 'Tài khoản này không được làm việc đó với bảng này.',
    'error.gone': 'Không còn bảng hay dòng này. Tải lại trang để lấy mô tả mới.',
    'error.conflict': 'Trùng với một dòng đã có, hoặc trỏ tới dòng không còn.',
    'error.blocked': 'Cổng bảo mật của Signet chặn nội dung vừa gửi. Bớt ký tự đặc biệt rồi thử lại.',
    'error.rateLimited': 'Gửi quá nhiều yêu cầu trong thời gian ngắn. Đợi một phút rồi thử lại.',
    'error.unavailable': 'API của Signet chưa trả lời. Thử lại sau ít phút.',
    'error.invalid': 'Dữ liệu bị cơ sở dữ liệu từ chối: kiểm tra lại các ô.',
    'error.rejected': 'Signet từ chối yêu cầu (HTTP {status}).',
    // câu chung của form dựng từ schema (schema-form.js); x-moc-ui.errors của từng trường thay câu chung
    'form.optional': 'không bắt buộc',
    'form.pick': '— Chọn —',
    'form.submit': 'Gửi',
    'form.yes': 'Có',
    'form.no': 'Không',
    'form.empty': '—',
    'form.top': 'Chưa gửi được, kiểm tra lại:',
    'form.required': 'Không được để trống',
    'form.between': 'Cần {min}–{max} ký tự',
    'form.minLength': 'Cần ít nhất {min} ký tự',
    'form.maxLength': 'Tối đa {max} ký tự',
    'form.minimum': 'Nhỏ nhất là {min}',
    'form.maximum': 'Lớn nhất là {max}',
    'form.minItems': 'Chọn ít nhất {min} mục',
    'form.maxItems': 'Chọn tối đa {max} mục',
    'form.uniqueItems': 'Có mục được chọn hai lần',
    'form.date': 'Ngày không có thật hoặc sai dạng',
    'form.format': 'Không đúng định dạng',
    'form.notAfterToday': 'Không được sau hôm nay',
    'form.notBeforeToday': 'Không được trước hôm nay',
    'form.range': 'Không được trước «{other}»',
    'form.nfc': 'Chữ tiếng Việt chưa ở dạng dựng sẵn (Unicode NFC)',
    'form.not': 'Có khoảng trắng thừa ở đầu hoặc cuối, xuống dòng hoặc ký tự ẩn',
    'form.enum': 'Không có trong danh sách',
    'form.const': 'Không đúng giá trị yêu cầu',
    'form.type': 'Sai kiểu dữ liệu',
    'form.additionalProperties': 'Trường không có trong mẫu',
    'form.invalid': 'Giá trị chưa hợp lệ',
    // schema dùng điều bộ kiểm không hiểu: báo lúc nạp (trang hiện qua error.loadForms)
    'schema.notObject': 'Schema {at}: phải là đối tượng',
    'schema.defs': 'Schema {at}: $defs phải là đối tượng',
    'schema.keyword': 'Schema {at}: không hỗ trợ từ khóa {key}',
    'schema.type': 'Schema {at}: kiểu {type} không có',
    'schema.format': 'Schema {at}: định dạng {format} không hỗ trợ (chỉ date, uuid)',
    'schema.shape': 'Schema {at}: {key} sai dạng ({value})',
    'schema.ref': 'Schema: $ref {ref} không trỏ tới #/$defs/… có sẵn',
    'schema.cycle': 'Schema: $ref vòng {path}',
    'schema.order': 'Schema: x-moc-order phải liệt kê đủ và đúng các trường trong properties',
    'schema.ranges': 'Schema: x-moc-range phải là mảng các cặp',
    'schema.range': 'Schema: x-moc-range {pair} phải là cặp hai trường format date',
    'schema.ui': 'Schema: x-moc-ui của {name} phải là đối tượng',
    'schema.widget': 'Schema: x-moc-ui.widget của {name} không có ({widget})',
    'schema.hidden': 'Schema: trường ẩn {name} bắt buộc mà không có giá trị',
  }),
  en: Object.freeze({
    'page.title': 'Apps generated from tables — Signet',
    'page.description': 'Signet — apps built automatically from tables described in Studio, API generated by PostgREST',
    'page.skip': 'Skip to main content',
    'page.brand': 'Apps from tables',
    'page.tagline': 'Signet · Studio + PostgREST',
    'page.footer': 'This page is not written for any particular table: the menu, lists and forms are built from the '
      + 'API description PostgREST generates for the tables in the sinh schema. Add a column in Studio and its field '
      + 'appears here right away.',
    'nav.apps': 'Applications',
    'nav.office': 'e-Office',
    'nav.logout': 'Sign out',
    'nav.tables': 'Apps generated from tables',
    'lang.switch': 'Tiếng Việt',
    'lang.other': 'vi',
    'status.signingIn': 'Signing in…',
    'status.signedIn': 'Signed in',
    'status.loading': 'Loading the table descriptions…',
    'status.redirecting': 'Redirecting to the sign-in page…',
    'apps.empty': 'No table in the sinh schema has a description (COMMENT ON TABLE) yet.',
    'list.heading': 'List',
    'list.empty': 'No rows yet.',
    'list.edit': 'Edit',
    'list.createdAt': 'Created {time}',
    'list.more': 'Showing the {shown} newest of {total} rows.',
    'create.heading': 'Add new',
    'create.submit': 'Add',
    'edit.heading': 'Edit row',
    'edit.submit': 'Save',
    'edit.cancel': 'Cancel',
    'notice.created': 'Added.',
    'notice.saved': 'Saved.',
    'report.view': 'View report',
    'report.close': 'Close report',
    'report.loading': 'Calculating…',
    'report.failed': 'Could not calculate the report: {error}',
    'report.empty': 'No rows to calculate yet.',
    'report.blank': '(blank)',
    'report.other': 'Other',
    'report.byMonth': '{column} (by month)',
    'report.count': 'Rows',
    'report.sum': 'Total {column}',
    'report.avg': 'Average {column}',
    'report.noTable': 'There is no table "{table}" in the sinh schema.',
    'report.noColumn': 'Table "{table}" has no column "{column}".',
    'report.badGroup': 'The group column "{column}" must be a list (enum) column or a date column.',
    'report.badOp': 'There is no calculation "{op}".',
    'report.needNumber': 'A total or an average needs a number column.',
    'report.badNumber': 'Column "{column}" is not a number column.',
    'error.loadSpec': 'Could not load the table descriptions: {error}',
    'error.loadRows': 'Could not load the list: {error}',
    'error.sendFailed': 'Not saved: {error}',
    'error.badForm': 'No form can be built for this table yet: {error}',
    'error.network': 'Could not reach Signet. Check your network connection and try again.',
    'error.session': 'Your session has expired. Reload the page to sign in again.',
    'error.forbidden': 'This account is not allowed to do that with this table.',
    'error.gone': 'This table or row no longer exists. Reload the page to get the new description.',
    'error.conflict': 'This duplicates an existing row or points to a row that no longer exists.',
    'error.blocked': 'The Signet security gateway blocked what was sent. Remove special characters and try again.',
    'error.rateLimited': 'Too many requests in a short time. Wait a minute and try again.',
    'error.unavailable': 'The Signet API is not responding. Try again in a few minutes.',
    'error.invalid': 'The database refused the data: check the fields again.',
    'error.rejected': 'Signet refused the request (HTTP {status}).',
    'error.rejected': 'Signet refused the request (HTTP {status}).',
    'form.optional': 'optional',
    'form.pick': '— Choose —',
    'form.submit': 'Submit',
    'form.yes': 'Yes',
    'form.no': 'No',
    'form.empty': '—',
    'form.top': 'Not sent yet. Please check:',
    'form.required': 'Required',
    'form.between': '{min}–{max} characters',
    'form.minLength': 'At least {min} characters',
    'form.maxLength': 'At most {max} characters',
    'form.minimum': 'At least {min}',
    'form.maximum': 'At most {max}',
    'form.minItems': 'Choose at least {min}',
    'form.maxItems': 'Choose at most {max}',
    'form.uniqueItems': 'An item is chosen twice',
    'form.date': 'Not a real date, or not in the right format',
    'form.format': 'Invalid format',
    'form.notAfterToday': 'Cannot be in the future',
    'form.notBeforeToday': 'Cannot be before today',
    'form.range': 'Cannot be before "{other}"',
    'form.nfc': 'Text is not in composed Unicode form (NFC)',
    'form.not': 'Extra spaces at the start or end, line breaks or hidden characters',
    'form.enum': 'Not in the list',
    'form.const': 'Not the required value',
    'form.type': 'Wrong data type',
    'form.additionalProperties': 'Field not in the form',
    'form.invalid': 'Invalid value',
    'schema.notObject': 'Schema {at}: must be an object',
    'schema.defs': 'Schema {at}: $defs must be an object',
    'schema.keyword': 'Schema {at}: keyword {key} is not supported',
    'schema.type': 'Schema {at}: type {type} does not exist',
    'schema.format': 'Schema {at}: format {format} is not supported (only date, uuid)',
    'schema.shape': 'Schema {at}: {key} has the wrong shape ({value})',
    'schema.ref': 'Schema: $ref {ref} does not point to an existing #/$defs/…',
    'schema.cycle': 'Schema: circular $ref {path}',
    'schema.order': 'Schema: x-moc-order must list exactly the fields in properties',
    'schema.ranges': 'Schema: x-moc-range must be an array of pairs',
    'schema.range': 'Schema: x-moc-range {pair} must be a pair of two fields with format date',
    'schema.ui': 'Schema: x-moc-ui of {name} must be an object',
    'schema.widget': 'Schema: x-moc-ui.widget of {name} does not exist ({widget})',
    'schema.hidden': 'Schema: hidden field {name} is required but has no value',
  }),
})

let current = 'vi'

/** 'en' khi đã chọn tiếng Anh, còn lại tiếng Việt: mặc định như Văn phòng điện tử. */
export function pickLocale(value) {
  return value === 'en' ? 'en' : 'vi'
}

export function locale() {
  return current
}

export function setLocale(value) {
  current = pickLocale(value)
  return current
}

const lookup = (table, key) => (Object.hasOwn(table, key) ? table[key] : undefined)

/** Câu theo khóa, {tên} thay bằng tham số cùng tên. lang bỏ trống là ngôn ngữ đang dùng; schema-form.js truyền ngôn
 *  ngữ của form. Thiếu bản tiếng Anh thì lấy tiếng Việt, thiếu cả hai thì trả khóa (test bắt trường hợp này trước khi
 *  tới trình duyệt). */
export function t(key, params = {}, lang = current) {
  const text = lookup(MESSAGES[pickLocale(lang)], key) ?? lookup(MESSAGES.vi, key) ?? key
  return text.replace(/\{(\w+)\}/g, (all, name) => (Object.hasOwn(params, name) ? String(params[name]) : all))
}

/** Ngôn ngữ đã lưu. storage() trả localStorage; trình duyệt chặn bộ nhớ cục bộ thì dùng tiếng Việt. */
export function savedLocale(storage = () => globalThis.localStorage) {
  try {
    return pickLocale(storage().getItem(STORAGE_KEY))
  } catch {
    return 'vi'
  }
}

export function saveLocale(value, storage = () => globalThis.localStorage) {
  try {
    storage().setItem(STORAGE_KEY, value)
  } catch {
    // trình duyệt chặn bộ nhớ cục bộ: chỉ đổi ở trang đang mở
  }
}

/** Gán câu cho phần tĩnh của trang theo ngôn ngữ đang dùng và đặt <html lang>. data-i18n="khóa" là chữ của phần
 *  tử (phần tử chỉ chứa chữ), data-i18n-<thuộc tính>="khóa" là thuộc tính, vd data-i18n-aria-label. */
export function localize(doc) {
  doc.documentElement.lang = current
  for (const node of doc.querySelectorAll('*')) {
    for (const { name, value } of [...node.attributes]) {
      if (name === 'data-i18n') node.textContent = t(value)
      else if (name.startsWith('data-i18n-')) node.setAttribute(name.slice('data-i18n-'.length), t(value))
    }
  }
}
