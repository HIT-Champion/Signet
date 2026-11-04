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

// Ứng dụng sinh từ bảng (#560): trang chung cho mọi bảng người vận hành tạo trong Studio ở schema sinh. Nạp mô tả API
// PostgREST tự sinh (GET /rest/v1/), mỗi bảng có COMMENT ON TABLE thành một mục menu; biểu mẫu thêm, sửa dựng bằng
// schema-form.js từ JSON Schema do openapi.js đổi ra; danh sách là PAGE dòng mới nhất. Không có mã riêng cho bảng
// nào: thêm cột trong Studio thì lần quay lại tab này (visibilitychange) nạp lại mô tả và ô mới hiện ngay, giữ chữ
// đang gõ. Chữ gán bằng textContent, không bao giờ gán HTML. Mỗi dòng của bảng bao_cao (#587) có nút xem báo cáo:
// bảng số luôn có, biểu đồ chỉ để nhìn (aria-hidden), độ dài thanh và màu gán qua el.style vì CSP chặn style=.

import { signIn, signOut } from './auth.js'
import { BAO_CAO, banhTron, duongBaoCao, ketQua, kiemKhaiBao, loiBaoCao, so, thanh } from './bao-cao.js'
import { locale, localize, saveLocale, savedLocale, setLocale, t } from './i18n.js'
import { apps, formSchema } from './openapi.js'
import { LOI, daSua, docThan, docTraLoi, duong, ngayGio, tenNguoi, tongSo, yeuCau } from './rest.js'
import { mountForm, summary } from './schema-form.js'

const el = (id) => document.getElementById(id)
const make = (tag, props = {}) => Object.assign(document.createElement(tag), props)

// Trạng thái trang. Tên người và hai dòng báo là hàm trả câu theo ngôn ngữ đang dùng, để đổi ngôn ngữ thì viết lại
const view = {
  nguoi: () => t('status.signingIn'),
  tin: () => t('status.loading'),
  loi: () => '',
  spec: null,       // mô tả API đã nạp
  bang: null,       // tên bảng đang mở
  form: null,       // {schema, key} của bảng đang mở
  rows: null,       // các dòng vừa tải; null khi chưa tải xong
  total: null,      // tổng số dòng theo Content-Range
  formMoi: null,    // form thêm mới đang hiện
  sua: null,        // {id, form} dòng đang sửa
  xem: null,        // {id, data, loi} báo cáo đang xem (bảng bao_cao): data là các dòng gộp, loi là hàm trả câu
}

/** Gọi /rest/v1 bằng token hiện tại → kết quả của docTraLoi, kèm tổng số dòng nếu có. */
async function goi(method, path, data) {
  const user = await signIn()
  if (!user) return { ok: false, message: t('status.redirecting') }
  const [url, init] = yeuCau(user.access_token, method, path, data)
  try {
    const res = await fetch(url, init)
    return { ...docTraLoi(res.status, docThan(await res.text())), total: tongSo(res.headers.get('Content-Range')) }
  } catch {
    return { ok: false, message: t(LOI.mang) }
  }
}

// --- thông báo: tin thường đọc lịch sự (role=status), lỗi đọc ngay (role=alert) ---
function thongBao() {
  el('tin').textContent = view.tin()
  el('loi').textContent = view.loi()
  el('loi').hidden = !el('loi').textContent
}
function baoTin(text) {
  view.tin = text
  view.loi = () => ''
  thongBao()
}
function baoLoi(text) {
  view.tin = () => ''
  view.loi = text
  thongBao()
}

const bangHash = () => decodeURIComponent(window.location.hash.replace(/^#\/?/, ''))

function veMenu() {
  const list = apps(view.spec)
  el('khong-co-bang').hidden = list.length > 0
  el('menu').replaceChildren(...list.map((a) => {
    const link = make('a', { className: 'tab', href: `#/${encodeURIComponent(a.table)}`, textContent: a.title })
    if (a.table === view.bang) link.setAttribute('aria-current', 'page')
    return link
  }))
  return list
}

/** Dựng phần đầu và form thêm mới của bảng đang mở. draft: chữ đang gõ dở, giữ khi vẽ lại. */
function veBang(draft) {
  const a = apps(view.spec).find((x) => x.table === view.bang)
  el('tieu-de-bang').textContent = a.title
  el('mo-ta-bang').textContent = a.help
  el('mo-ta-bang').hidden = !a.help
  view.form = formSchema(view.spec, view.bang)
  try {
    view.formMoi = mountForm(el('form-moi'), view.form.schema, {
      lang: locale(), draft, idPrefix: 'moi-', submitLabel: t('create.submit'), onSubmit: them,
    })
  } catch (err) {
    // mountForm ném lỗi khi schema không dùng được (vd kiểu cột lạ): báo, không vẽ form hỏng
    el('form-moi').replaceChildren()
    view.formMoi = null
    baoLoi(() => t('error.badForm', { error: err.message }))
  }
}

function veDong() {
  const { schema, key } = view.form
  const rows = view.rows ?? []
  el('danh-sach').replaceChildren(...rows.map((row) => {
    const li = make('li', { className: 'the' })
    const dl = make('dl', { className: 'chi-tiet' })
    for (const r of summary(schema, row, locale())) {
      dl.append(make('dt', { textContent: r.label }), make('dd', { textContent: r.value }))
    }
    const dau = make('div', { className: 'the-dau' })
    const nutDong = make('div', { className: 'nut-dong' })   // các nút của dòng đứng cạnh nhau ở bên phải
    dau.append(make('span', { className: 'gio', textContent: t('list.createdAt', { time: ngayGio(row.created_at) }) }),
      nutDong)
    const dangSua = key !== null && view.sua !== null && view.sua.id === row[key]
    if (key !== null && !dangSua) {
      const nut = make('button', { type: 'button', className: 'btn ghost', textContent: t('list.edit') })
      nut.addEventListener('click', () => moSua(row))
      nutDong.append(nut)
    }
    const dangXem = key !== null && view.xem !== null && view.xem.id === row[key]
    if (view.bang === BAO_CAO && key !== null) {
      const nut = make('button', { type: 'button', className: 'btn ghost',
        textContent: dangXem ? t('report.close') : t('report.view') })
      nut.setAttribute('aria-expanded', String(dangXem))
      nut.addEventListener('click', () => (dangXem ? dongBaoCao() : xemBaoCao(row)))
      nutDong.append(nut)
    }
    li.append(dau, dl)
    if (dangXem) li.append(veBaoCao(row))
    if (dangSua) li.append(formSua(row))
    return li
  }))
  el('khong-co-dong').hidden = view.rows === null || rows.length > 0
  const more = view.total !== null && view.total > rows.length
  el('dem-dong').hidden = !more
  el('dem-dong').textContent = more ? t('list.more', { shown: rows.length, total: view.total }) : ''
}

function formSua(row) {
  const box = make('div', { className: 'khung-form' })
  box.append(make('h2', { textContent: t('edit.heading') }))
  const holder = make('div')
  const huy = make('button', { type: 'button', className: 'btn ghost', textContent: t('edit.cancel') })
  huy.addEventListener('click', () => {
    view.sua = null
    veDong()
  })
  box.append(holder, huy)
  const draft = view.sua.form?.values()
  view.sua.form = mountForm(holder, view.form.schema, {
    lang: locale(), values: row, draft, idPrefix: 'sua-', submitLabel: t('edit.submit'), onSubmit: luuSua,
  })
  return box
}

function moSua(row) {
  view.sua = { id: row[view.form.key], form: null }
  veDong()
  document.getElementById(`sua-${view.form.schema['x-moc-order'][0]}`)?.focus()
}

// --- báo cáo động (#587) ---

/** Khung báo cáo của một khai báo: câu báo lỗi, "đang tính", hoặc bảng số kèm biểu đồ theo kiểu hiện. */
function veBaoCao(row) {
  const box = make('div', { className: 'bao-cao' })
  const kb = kiemKhaiBao(view.spec, row)
  const loi = !kb.ok ? kb.message : view.xem.loi?.()
  if (loi) {
    box.append(make('p', { className: 'loi', textContent: loi }))
    return box
  }
  if (view.xem.data === null) {
    box.append(make('p', { className: 'status', textContent: t('report.loading') }))
    return box
  }
  const items = ketQua(kb, view.xem.data)
  if (!items.length) {
    box.append(make('p', { className: 'empty', textContent: t('report.empty') }))
    return box
  }
  box.append(bangSo(row.ten, kb, items))
  const ve = { bar: veCot, pie: veTron }[kb.kieu]
  const hinh = ve?.(items)
  if (hinh) {
    hinh.setAttribute('aria-hidden', 'true')   // bảng số ở trên đã có đủ số liệu cho máy đọc màn hình
    box.append(hinh)
  }
  return box
}

function bangSo(tieuDe, kb, items) {
  const table = make('table', { className: 'bang-so' })
  table.append(make('caption', { textContent: tieuDe ?? '' }))
  const giaTri = {
    count: () => t('report.count'),
    sum: () => t('report.sum', { column: kb.tenCot }),
    avg: () => t('report.avg', { column: kb.tenCot }),
  }[kb.phep]()
  const nhom = kb.giaTri ? kb.tenNhom : t('report.byMonth', { column: kb.tenNhom })
  const dau = make('tr')
  dau.append(make('th', { scope: 'col', textContent: nhom }), make('th', { scope: 'col', textContent: giaTri }))
  const than = make('tbody')
  than.append(...items.map((x) => {
    const tr = make('tr')
    tr.append(make('th', { scope: 'row', textContent: x.nhan }), make('td', { textContent: so(x.giaTri, locale()) }))
    return tr
  }))
  table.append(make('thead'), than)
  table.tHead.append(dau)
  return table
}

function veCot(items) {
  const rong = thanh(items)
  const box = make('div', { className: 'bd-cot' })
  items.forEach((x, i) => {
    const ray = make('div', { className: 'ray' })
    const bar = make('div', { className: 'thanh' })
    bar.style.width = `${rong[i]}%`
    ray.append(bar)
    box.append(make('span', { textContent: x.nhan }), ray, make('span', { textContent: so(x.giaTri, locale()) }))
  })
  return box
}

function veTron(items) {
  const banh = banhTron(items)
  if (!banh) return null
  const box = make('div', { className: 'bd-tron' })
  const dia = make('div', { className: 'dia' })
  dia.style.background = banh.nen
  const chu = make('ul', { className: 'chu-giai' })
  chu.append(...banh.lat.map((x) => {
    const o = make('span', { className: 'o' })
    o.style.background = x.mau
    const li = make('li')
    li.append(o, make('span', { textContent: `${x.nhan}: ${so(x.giaTri, locale())}` }))
    return li
  }))
  box.append(dia, chu)
  return box
}

async function xemBaoCao(row) {
  const id = row[view.form.key]
  view.xem = { id, data: null, loi: null }
  veDong()
  const kb = kiemKhaiBao(view.spec, row)
  if (!kb.ok) return                      // veBaoCao đã hiện câu báo, không gửi truy vấn sai
  const kq = await goi('GET', duongBaoCao(kb))
  if (view.xem?.id !== id) return         // đã đóng hay chuyển bảng lúc đang tính
  if (kq.ok) view.xem.data = Array.isArray(kq.data) ? kq.data : []
  else view.xem.loi = () => loiBaoCao(kq)
  veDong()
}

function dongBaoCao() {
  view.xem = null
  veDong()
}

async function taiDong() {
  const bang = view.bang
  const kq = await goi('GET', duong.rows(bang))
  if (bang !== view.bang) return          // đã chuyển bảng khác lúc đang tải
  if (!kq.ok) {
    baoLoi(() => t('error.loadRows', { error: kq.message }))
    return
  }
  view.rows = Array.isArray(kq.data) ? kq.data : []
  view.total = kq.total
  veDong()
}

async function them(data) {
  const kq = await goi('POST', duong.create(view.bang), data)
  if (!kq.ok) {
    baoLoi(() => t('error.sendFailed', { error: kq.message }))
    return
  }
  view.formMoi.reset()
  baoTin(() => t('notice.created'))
  await taiDong()
}

async function luuSua(data) {
  const kq = daSua(await goi('PATCH', duong.row(view.bang, view.form.key, view.sua.id), data))
  if (!kq.ok) {
    baoLoi(() => t('error.sendFailed', { error: kq.message }))
    return
  }
  if (view.xem?.id === view.sua.id) view.xem = null   // khai báo vừa đổi: số đang hiện đã cũ
  view.sua = null
  baoTin(() => t('notice.saved'))
  await taiDong()
}

/** Mở bảng theo tên (bảng không có trong menu thì mở bảng đầu tiên). */
function moBang(table, { focus = true } = {}) {
  const list = apps(view.spec)
  view.bang = list.some((a) => a.table === table) ? table : (list[0]?.table ?? null)
  view.rows = null
  view.total = null
  view.sua = null
  view.xem = null
  veMenu()
  el('bang').hidden = view.bang === null
  if (view.bang === null) return
  veBang()
  veDong()
  if (focus) el('tieu-de-bang').focus()
  taiDong()
}

/** Quay lại tab: nạp lại mô tả API; bảng đổi (thêm cột trong Studio) thì vẽ lại, giữ chữ đang gõ ở form thêm mới. */
async function napLaiMoTa() {
  if (document.visibilityState !== 'visible' || !view.spec) return
  const kq = await goi('GET', duong.spec())
  if (!kq.ok || !kq.data?.definitions) return
  if (JSON.stringify(kq.data.definitions) === JSON.stringify(view.spec.definitions)) return
  const draft = view.formMoi?.values()
  view.spec = kq.data
  if (!apps(view.spec).some((a) => a.table === view.bang)) {
    moBang(view.bang, { focus: false })
    return
  }
  veMenu()
  view.sua = null
  veBang(draft)
  veDong()
  taiDong()
}

/** Nút đổi ngôn ngữ: lưu lựa chọn, gán lại phần tĩnh rồi vẽ lại phần đang hiện, giữ chữ đang gõ. */
function switchLocale() {
  saveLocale(setLocale(locale() === 'vi' ? 'en' : 'vi'))
  localize(document)
  el('nguoi').textContent = view.nguoi()
  thongBao()
  if (!view.bang) return
  veBang(view.formMoi?.values())
  veDong()
}

async function main() {
  setLocale(savedLocale())
  localize(document)
  el('doi-ngon-ngu').addEventListener('click', switchLocale)
  const user = await signIn()
  if (!user) return
  view.nguoi = () => tenNguoi(user.access_token) || t('status.signedIn')
  el('nguoi').textContent = view.nguoi()
  el('thoat').hidden = false
  el('thoat').addEventListener('click', () => signOut())

  const kq = await goi('GET', duong.spec())
  if (!kq.ok || !kq.data?.definitions) {
    baoLoi(() => t('error.loadSpec', { error: kq.message || t('error.unavailable') }))
    return
  }
  view.spec = kq.data
  baoTin(() => '')
  el('ung-dung').hidden = false
  moBang(bangHash(), { focus: false })
  window.addEventListener('hashchange', () => moBang(bangHash()))
  document.addEventListener('visibilitychange', napLaiMoTa)
}

main()
