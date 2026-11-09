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

// Phần thuần của trang Đơn nghỉ phép (public/don.js, node --test, không cần trình duyệt), kèm kiểm khớp: formKey,
// process id ↔ app.yaml và BPMN; trường trang đọc ↔ forms/*.json; trang chỉ dựng form qua một hàm; màu đủ tương phản.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

import {
  API, FORM_DON, FORM_DUYET, LOI, MA_LOI, OFFSET_TOI_DA, QUY_TRINH, TRANG, conTrang, docThan, docTraLoi, doiChieu,
  duong, ghepDon, huyDuoc, ngayGio, sapXepDon, sapXepViec, nguoiGui, soNgay, tenNguoi, trangThai, yeuCau,
} from '../public/don.js'
import { t } from '../public/i18n.js'

const APP = new URL('../', import.meta.url)
const ROOT = new URL('../../../', import.meta.url)
const read = (base, path) => readFileSync(new URL(path, base), 'utf8')

test('lời gọi API chung: đường, token, thân {"data": …}', () => {
  const [url, init] = yeuCau('tok', 'POST', duong.guiDon(), { loai: 'om' })
  assert.equal(url, '/api/workflow/nghi-phep/processes/nghi-phep.don')
  assert.equal(init.method, 'POST')
  assert.equal(init.headers.Authorization, 'Bearer tok')
  assert.equal(init.headers['Content-Type'], 'application/json')
  assert.deepEqual(JSON.parse(init.body), { data: { loai: 'om' } })
  const [list, get] = yeuCau('tok', 'GET', duong.viec())
  assert.equal(list, `${API}/tasks`)
  assert.equal(get.body, undefined)
  assert.equal(get.headers['Content-Type'], undefined)
  assert.equal(`${API}${duong.form(FORM_DUYET)}`, '/api/workflow/nghi-phep/forms/nghi-phep.duyet')
  // Đơn của tôi theo trang, hủy đơn (#325, hợp đồng K1, K2)
  assert.equal(duong.donCuaToi(), '/processes?limit=50&offset=0')
  assert.equal(duong.donCuaToi(100), '/processes?limit=50&offset=100')
  const [huy, del] = yeuCau('tok', 'DELETE', duong.huyDon('7d2c1e0a-0000-4000-8000-000000000001'))
  assert.equal(huy, `${API}/processes/7d2c1e0a-0000-4000-8000-000000000001`)
  assert.deepEqual([del.method, del.body, del.headers['Content-Type']], ['DELETE', undefined, undefined])
  assert.equal(duong.huyDon('a/../b?c'), '/processes/a%2F..%2Fb%3Fc')
  // mã việc lạ không thoát ra khỏi đường
  assert.equal(duong.xongViec('a/../b?c'), '/tasks/a%2F..%2Fb%3Fc')
})

test('trả lời: 2xx là xong, 422 giữ lỗi từng trường, mã khác thành câu đọc được', () => {
  assert.deepEqual(docTraLoi(201, { id: 'p1' }), { ok: true, data: { id: 'p1' } })
  assert.deepEqual(docTraLoi(204, null), { ok: true, data: null })
  const bad = docTraLoi(422, { errors: { denNgay: 'x-moc-range' } })
  assert.equal(bad.ok, false)
  assert.deepEqual(bad.errors, { denNgay: 'x-moc-range' })
  assert.equal(bad.status, 422)
  for (const status of [401, 403, 404, 409, 429]) {
    assert.deepEqual(docTraLoi(status, { error: 'x' }), { ok: false, status, message: t(LOI[status]) })
  }
  assert.equal(docTraLoi(503, null).message, t(LOI[500]))
  assert.match(docTraLoi(418, null).message, /HTTP 418/)
  // 422 không mang lỗi từng trường (cổng, WAF) thì không giả làm lỗi của form
  for (const body of [null, { errors: [] }, { errors: 'sai' }, { detail: 'x' }]) {
    assert.equal(docTraLoi(422, body).errors, undefined, JSON.stringify(body))
  }
  assert.equal(docThan(''), null)
  assert.equal(docThan('<html>502</html>'), null)
  assert.deepEqual(docThan('{"id":"p1"}'), { id: 'p1' })
})

test('trạng thái đơn theo lúc kết thúc và quyết định của trưởng phòng', () => {
  assert.deepEqual(trangThai({ endedAt: null, data: {} }), { ma: 'cho', nhan: 'Đang chờ duyệt' })
  // quyết định chưa chốt (quy trình còn chạy) thì vẫn là chờ
  assert.equal(trangThai({ endedAt: null, data: { quyetDinh: 'dong-y' } }).ma, 'cho')
  assert.deepEqual(trangThai({ endedAt: '2026-10-26T03:00:00Z', data: { quyetDinh: 'dong-y' } }),
    { ma: 'dong-y', nhan: 'Đã duyệt' })
  assert.equal(trangThai({ endedAt: '2026-10-26T03:00:00Z', data: { quyetDinh: 'tu-choi' } }).nhan, 'Bị từ chối')
  assert.equal(trangThai({ endedAt: '2026-10-26T03:00:00Z', data: null }).ma, 'xong')
  assert.equal(trangThai(undefined).ma, 'cho')
  // đã hủy (#325): lõi đặt cả endedAt lẫn cancelled
  assert.deepEqual(trangThai({ endedAt: '2026-11-09T03:15:00Z', cancelled: true, data: {} }),
    { ma: 'huy', nhan: 'Đã hủy' })
  assert.equal(trangThai({ endedAt: '2026-11-09T03:15:00Z', cancelled: false, data: { quyetDinh: 'dong-y' } }).ma,
    'dong-y')
})

// ba mục của k1-mau.json (hợp đồng K2 của phiên Vượng): đang chờ, đã hủy, đã duyệt
const MAU = [
  { id: 'p1', startedAt: '2026-11-10T01:20:00.000+07:00', endedAt: null, cancelled: false, data: { soNgayLam: 2 } },
  { id: 'p2', startedAt: '2026-11-09T09:00:00.000+07:00', endedAt: '2026-11-09T10:15:00.000+07:00', cancelled: true,
    data: { soNgayLam: 1 } },
  { id: 'p3', startedAt: '2026-11-05T08:00:00.000+07:00', endedAt: '2026-11-05T14:00:00.000+07:00', cancelled: false,
    data: { quyetDinh: 'dong-y' } },
]

test('hủy đơn (#325): chỉ đơn đang chờ; 404, 409 của lõi có câu riêng', () => {
  assert.deepEqual(MAU.map(huyDuoc), [true, false, false])
  assert.equal(huyDuoc({ endedAt: null }), true, 'lõi cũ chưa có cancelled')
  assert.equal(huyDuoc(undefined), true)
  const gone = docTraLoi(404, { detail: { code: 'process_not_found', message: 'Đơn không còn' } })
  assert.deepEqual(gone, { ok: false, status: 404, message: t('error.cancelGone') })
  const done = docTraLoi(409, { detail: { code: 'already_finished', message: 'Đơn đã xong' } })
  assert.deepEqual(done, { ok: false, status: 409, message: t('error.alreadyFinished') })
  assert.match(done.message, /không hủy được/)
  // mã lạ, detail không phải đối tượng (lỗi kiểm tham số của FastAPI là mảng), tên trùng thuộc tính của Object: câu
  // theo mã HTTP như cũ
  for (const detail of [{ code: 'task_not_found' }, [{ loc: ['query', 'limit'] }], 'x', { code: 'constructor' }]) {
    assert.equal(docTraLoi(404, { detail }).message, t(LOI[404]), JSON.stringify(detail))
  }
  for (const key of Object.values(MA_LOI)) assert.notEqual(t(key), key)
})

test('Đơn của tôi theo trang (#325): còn trang khi đủ TRANG mục; ghép trang không nhân đôi, bản mới thắng', () => {
  assert.equal(TRANG, 50)
  assert.equal(conTrang(Array.from({ length: TRANG }, (_, i) => ({ id: `d${i}` }))), true)
  assert.equal(conTrang(MAU), false)
  assert.equal(conTrang(null), false)
  // lõi nhận offset tới 10000: trang bắt đầu ở 9950 đủ mục thì vẫn còn trang 10000, ở 10000 thì thôi
  const du = Array.from({ length: TRANG }, (_, i) => ({ id: `d${i}` }))
  assert.equal(conTrang(du, OFFSET_TOI_DA - TRANG), true)
  assert.equal(conTrang(du, OFFSET_TOI_DA), false)
  // đơn mới gửi chen vào đầu: trang sau lặp lại p3; p1 vừa được duyệt thì lấy bản mới
  const moi = [{ ...MAU[0], endedAt: '2026-11-10T02:00:00.000+07:00', data: { quyetDinh: 'tu-choi' } },
    { id: 'p0', startedAt: '2026-11-10T03:00:00.000+07:00', endedAt: null, data: {} }]
  const ghep = ghepDon(MAU, moi)
  assert.deepEqual(ghep.map((d) => d.id), ['p0', 'p1', 'p2', 'p3'])
  assert.equal(trangThai(ghep[1]).ma, 'tu-choi')
  assert.deepEqual(ghepDon(MAU, [MAU[2]]).map((d) => d.id), ['p1', 'p2', 'p3'])
  assert.deepEqual(MAU.map((d) => d.id), ['p1', 'p2', 'p3'], 'không sửa mảng gốc')
})

test('số ngày nghỉ tính cả hai đầu; ngày sai, ngược thì không có', () => {
  assert.equal(soNgay('2026-10-27', '2026-10-27'), 1)
  assert.equal(soNgay('2026-10-27', '2026-10-29'), 3)
  assert.equal(soNgay('2026-12-30', '2027-01-02'), 4)
  assert.equal(soNgay('2028-02-28', '2028-03-01'), 3)          // năm nhuận
  assert.equal(soNgay('2026-10-29', '2026-10-27'), null)
  assert.equal(soNgay('2026-02-30', '2026-03-01'), null)
  assert.equal(soNgay('27/10/2026', '2026-10-29'), null)
  assert.equal(soNgay(undefined, '2026-10-29'), null)
})

test('giờ Việt Nam; thứ tự đơn, thứ tự việc', () => {
  assert.equal(ngayGio('2026-10-26T07:05:00Z'), '26/10/2026 14:05')
  assert.equal(ngayGio('khong-phai-gio'), '')
  assert.equal(ngayGio(null), '')
  const don = [{ id: 'a', startedAt: '2026-10-20T01:00:00Z' }, { id: 'b', startedAt: '2026-10-25T01:00:00Z' },
    { id: 'c', startedAt: null }]
  assert.deepEqual(sapXepDon(don).map((d) => d.id), ['b', 'a', 'c'])
  assert.deepEqual(don.map((d) => d.id), ['a', 'b', 'c'])                    // không sửa mảng gốc
  const viec = [{ id: 'x', createdAt: '2026-10-25T01:00:00Z' }, { id: 'y', createdAt: '2026-10-20T01:00:00Z' }]
  assert.deepEqual(sapXepViec(viec).map((t) => t.id), ['y', 'x'])
})

test('làm mới việc cần duyệt: thêm việc mới, bỏ việc đã xong, giữ thẻ đang mở', () => {
  const moi = [{ id: 't3', createdAt: '2026-10-26T02:00:00Z' }, { id: 't1', createdAt: '2026-10-26T01:00:00Z' },
    { id: 't4', createdAt: '2026-10-26T00:00:00Z' }]
  assert.deepEqual(doiChieu(['t1', 't2'], moi), { them: [moi[2], moi[0]], bo: ['t2'] })
  assert.deepEqual(doiChieu([], []), { them: [], bo: [] })
  assert.deepEqual(doiChieu(['t1'], []), { them: [], bo: ['t1'] })
})

test('tên trong token có dấu tiếng Việt, token hỏng thì rỗng', () => {
  const part = Buffer.from(JSON.stringify({ name: 'Vũ Thị Mai', preferred_username: 'mai' })).toString('base64url')
  assert.equal(tenNguoi(`h.${part}.s`), 'Vũ Thị Mai')
  const only = Buffer.from(JSON.stringify({ preferred_username: 'mai' })).toString('base64url')
  assert.equal(tenNguoi(`h.${only}.s`), 'mai')
  for (const token of ['khong-phai-token', `h.${Buffer.from('[1]').toString('base64url')}.s`, undefined]) {
    assert.equal(tenNguoi(token), '')
  }
})

test('formKey, process id khớp app.yaml, BPMN và tệp form; trường trang đọc có trong form', () => {
  const manifest = read(APP, 'app.yaml')
  const keys = [...manifest.matchAll(/^ {4}(nghi-phep\.[a-z-]+): (\S+)$/gm)]
  const forms = Object.fromEntries(keys.map((m) => [m[1], m[2]]))
  assert.deepEqual(forms, { [FORM_DON]: 'forms/don.json', [FORM_DUYET]: 'forms/duyet.json' })
  assert.match(manifest, /^path: \/nghi-phep$/m)
  const bpmn = read(APP, 'workflow/don-nghi-phep.bpmn20.xml')
  assert.match(bpmn, new RegExp(`<process id="${QUY_TRINH.replace('.', '\\.')}"`))
  assert.match(bpmn, new RegExp(`<startEvent [^>]*flowable:formKey="${FORM_DON}"`))
  assert.match(bpmn, new RegExp(`<userTask [^>]*flowable:formKey="${FORM_DUYET}"`))
  const don = JSON.parse(read(APP, forms[FORM_DON]))
  const duyet = JSON.parse(read(APP, forms[FORM_DUYET]))
  for (const name of ['tuNgay', 'denNgay', 'soNgayLam']) assert.ok(don.properties[name], `forms/don.json thiếu ${name}`)
  assert.deepEqual(duyet.properties.quyetDinh.enum, ['dong-y', 'tu-choi'])
  // nhánh của các cổng rẽ đúng các giá trị quyết định của form (cổng của trưởng phòng còn chia theo số ngày)
  const conditions = [...bpmn.matchAll(/\$\{quyetDinh == '([a-z-]+)'(?: && soNgayLam [<>]=? 3)?\}/g)].map((m) => m[1])
  assert.deepEqual([...new Set(conditions)].sort(), [...duyet.properties.quyetDinh.enum].sort())
})

test('trang không có script nội tuyến, không innerHTML; form chỉ dựng qua một hàm; đăng nhập đúng client', () => {
  const html = read(APP, 'public/index.html')
  assert.doesNotMatch(html, /<script(?![^>]*\bsrc=)[^>]*>/)
  assert.doesNotMatch(html, /\son[a-z]+=/i)
  for (const id of ['tieu-de-gui-don', 'tieu-de-don-cua-toi', 'tieu-de-viec-can-duyet']) {
    assert.match(html, new RegExp(`<h1 id="${id}" tabindex="-1"[^>]*>`))
  }
  assert.match(html, /role="status"/)
  assert.match(html, /role="alert"/)
  const app = read(APP, 'public/app.js')
  assert.doesNotMatch(app, /innerHTML|insertAdjacentHTML|document\.write/)
  assert.equal(app.match(/mountForm\(/g).length, 1, 'chỉ veForm() gọi mountForm')
  assert.equal(app.match(/summary\(/g).length, 1, 'chỉ tomTat() gọi summary')
  // hủy đơn hỏi lại bằng <dialog> modal (#325): Esc, "Không hủy" là thôi; nút mặc định là "Không hủy"
  assert.match(html,
    /<dialog id="hoi-huy" aria-labelledby="hoi-huy-tieu-de" aria-describedby="hoi-huy-chu">\s*<form method="dialog">/)
  assert.match(html, /<button type="submit" value="co" class="btn nguy" data-i18n="cancel\.yes">/)
  assert.match(html, /<button type="submit" value="khong" class="btn ghost" data-i18n="cancel\.no" autofocus>/)
  assert.match(html, /<button id="xem-them-don" type="button"[^>]* hidden>/)
  assert.match(app, /hop\.showModal\(\)/)
  assert.match(app, /returnValue === 'co'/)
  assert.match(app, /setAttribute\('aria-label', t\('mine\.cancelLabel'/)
  const auth = read(APP, 'public/auth.js')
  assert.match(auth, /const CALLBACK = '\/nghi-phep\/dang-nhap'/)
  assert.match(auth, /response_mode: 'fragment'/)
  assert.match(auth, /clientId: 'app-nghi-phep'/)
  const pkg = JSON.parse(read(APP, 'package.json'))
  const ref = JSON.parse(read(ROOT, 'apps/bang-tin/package.json'))
  assert.equal(pkg.dependencies['oidc-client-ts'], ref.dependencies['oidc-client-ts'])
})

function contrast(a, b) {
  const lum = (hex) => {
    const [r, g, bl] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255)
      .map((c) => (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4))
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl
  }
  const [hi, lo] = [lum(a), lum(b)].sort((x, y) => y - x)
  return (hi + 0.05) / (lo + 0.05)
}

test('các cặp chữ/nền của style.css đạt WCAG AA (4,5:1)', () => {
  const css = read(APP, 'public/style.css')
  const v = Object.fromEntries([...css.matchAll(/--([a-z0-9-]+): (#[0-9a-f]{6});/g)].map((m) => [m[1], m[2]]))
  const pairs = [['stone-900', 'stone-50'], ['stone-600', 'stone-50'], ['stone-600', 'butter'], ['brand-800', 'butter'],
    ['red-700', 'red-50'], ['green-800', 'green-50'], ['amber-800', 'amber-50'], ['stone-900', 'stone-100']]
  for (const [fg, bg] of pairs) assert.ok(contrast(v[fg], v[bg]) >= 4.5, `${fg} trên ${bg}`)
  for (const bg of ['brand-700', 'brand-800', 'red-700']) {
    assert.ok(contrast('#ffffff', v[bg]) >= 4.5, `chữ trắng trên ${bg}`)
  }
  assert.ok(contrast(v['stone-600'], '#ffffff') >= 4.5)
  assert.ok(contrast(v.focus, v['stone-50']) >= 3, 'viền tiêu điểm')
})

test('tên người gửi của việc cần duyệt lấy từ initiatorName của lõi; thiếu, rỗng hay sai kiểu thì rỗng (#506)', () => {
  assert.equal(nguoiGui({ id: 't1', initiatorName: ' Vũ Thị Mai ' }), 'Vũ Thị Mai')
  for (const task of [{ id: 't1' }, { initiatorName: null }, { initiatorName: '  ' }, { initiatorName: 7 }, null]) {
    assert.equal(nguoiGui(task), '')
  }
})
