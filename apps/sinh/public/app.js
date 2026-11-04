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
// đang gõ. Chữ gán bằng textContent, không bao giờ gán HTML. Bảng có mẫu in (bảng mau_in, #586) thì mỗi dòng có nút In:
// svc-files dựng PDF bằng token của người dùng, trang tải về.

import { signIn, signOut } from './auth.js'
import { locale, localize, saveLocale, savedLocale, setLocale, t } from './i18n.js'
import { apps, formSchema } from './openapi.js'
import { LOI, daSua, docThan, docTraLoi, duong, duongIn, loiIn, ngayGio, tenNguoi, tongSo, yeuCau } from './rest.js'
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
  mau: [],          // [{id, ten}] mẫu in của bảng đang mở
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
    // svc-files lấy dòng bằng id=eq.<id>: chỉ bảng có khóa chính là cột id (mặc định của Studio) mới in được
    if (key === 'id' && view.mau.length && duongIn(view.bang, row.id, view.mau[0].id)) nutDong.append(nutIn(row))
    li.append(dau, dl)
    if (dangSua) li.append(formSua(row))
    return li
  }))
  el('khong-co-dong').hidden = view.rows === null || rows.length > 0
  const more = view.total !== null && view.total > rows.length
  el('dem-dong').hidden = !more
  el('dem-dong').textContent = more ? t('list.more', { shown: rows.length, total: view.total }) : ''
}

/** Nút In của một dòng; bảng có nhiều mẫu thì kèm ô chọn mẫu theo tên. */
function nutIn(row) {
  const box = make('span', { className: 'in' })
  let chon = null
  if (view.mau.length > 1) {
    chon = make('select', { className: 'chon-mau' })
    chon.setAttribute('aria-label', t('print.template'))
    chon.append(...view.mau.map((m) => make('option', { value: String(m.id), textContent: m.ten || `#${m.id}` })))
    box.append(chon)
  }
  const nut = make('button', { type: 'button', className: 'btn ghost', textContent: t('print.button') })
  nut.addEventListener('click', () => inDong(row, chon ? Number(chon.value) : view.mau[0].id, nut))
  box.append(nut)
  return box
}

/** Xin svc-files PDF của dòng theo mẫu, kèm token; được thì tải về tên <bảng>-<id>.pdf. */
async function inDong(row, mau, nut) {
  if (nut.getAttribute('aria-disabled') === 'true') return      // đang in: bấm thêm không gửi lần nữa
  const user = await signIn()
  if (!user) return
  const bang = view.bang
  const id = row.id
  nut.setAttribute('aria-disabled', 'true')
  try {
    const res = await fetch(duongIn(bang, id, mau), {
      headers: { Authorization: `Bearer ${user.access_token}` }, cache: 'no-store',
    })
    if (!res.ok || !/^application\/pdf\b/.test(res.headers.get('Content-Type') ?? '')) {
      const body = docThan(await res.text())
      baoLoi(() => t('print.failed', { error: loiIn(res.status, body) }))
      return
    }
    const url = URL.createObjectURL(await res.blob())
    const a = make('a', { href: url, download: `${bang}-${id}.pdf` })
    document.body.append(a)
    a.click()
    a.remove()
    setTimeout(() => URL.revokeObjectURL(url), 60_000)
    baoTin(() => t('print.done'))
  } catch {
    baoLoi(() => t('print.failed', { error: t(LOI.mang) }))
  } finally {
    nut.removeAttribute('aria-disabled')
  }
}

/** Mẫu in của bảng đang mở (K4). Bản cài chưa có bảng mau_in (404) hay lỗi khác: không có nút In, không báo lỗi. */
async function taiMau() {
  const bang = view.bang
  const kq = await goi('GET', duong.mau(bang))
  if (bang !== view.bang) return
  view.mau = kq.ok && Array.isArray(kq.data) ? kq.data.filter((m) => duongIn(bang, 1, m?.id)) : []
  if (view.mau.length) veDong()
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
  view.mau = []
  veMenu()
  el('bang').hidden = view.bang === null
  if (view.bang === null) return
  veBang()
  veDong()
  if (focus) el('tieu-de-bang').focus()
  taiDong()
  taiMau()
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
