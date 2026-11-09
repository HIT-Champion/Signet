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

// Đơn nghỉ phép: đăng nhập, nạp hai form từ lõi (JSON Schema), vẽ ba phần — Gửi đơn, Đơn của tôi, Việc cần duyệt (chỉ
// hiện khi có việc). Mọi dữ liệu đi qua API quy trình chung của lõi bằng token của người dùng; lõi kiểm lại form và
// quyết định ai thấy việc nào. Chữ gán bằng textContent, không bao giờ gán HTML. Chữ lấy từ bảng dịch vi/en
// (i18n.js); phần đang hiện giữ lại để đổi ngôn ngữ thì vẽ lại ngay, không mất chữ đang gõ trong form.

import { signIn, signOut } from './auth.js'
import {
  FORM_DON, FORM_DUYET, LOI, TRANG, conTrang, docThan, docTraLoi, doiChieu, duong, ghepDon, huyDuoc, ngayGio, nguoiGui,
  sapXepDon, soNgay, tenNguoi, trangThai, yeuCau,
} from './don.js'
import { locale, localize, saveLocale, savedLocale, setLocale, t } from './i18n.js'
import { mountForm, summary } from './schema-form.js'

const el = (id) => document.getElementById(id)
const make = (tag, props = {}) => Object.assign(document.createElement(tag), props)
const LAM_MOI_MS = 30000

// Phần đang hiện. Tên người và hai dòng báo là hàm trả câu theo ngôn ngữ đang dùng; forms: hai mẫu đã nạp; don: đơn
// của tôi đã tải (null khi chưa tải xong lần nào); tiep: offset của trang sau, null khi hết; xemThem: số lần đã bấm
// "Xem thêm"; formDon: form gửi đơn đang hiện
const view = {
  nguoi: () => t('status.signingIn'),
  tin: () => t('status.loadingForms'),
  loi: () => '',
  forms: null,
  don: null,
  tiep: null,
  xemThem: 0,
  formDon: null,
}

// Mọi chỗ dựng form, tóm tắt đơn đi qua hai hàm này: giao diện của schema-form.js đổi thì chỉ sửa ở đây. Cả hai theo
// ngôn ngữ đang dùng: nhãn, lựa chọn, gợi ý lấy {vi, en} trong x-moc-ui của tệp form, câu chung lấy từ i18n.js
function veForm(container, schema, { idPrefix, submitLabel, onSubmit, draft }) {
  return mountForm(container, schema, { lang: locale(), draft, idPrefix, submitLabel, onSubmit })
}
function tomTat(schema, data) {
  return summary(schema, data, locale())
}

/** Gọi API chung của lõi bằng token hiện tại → kết quả của docTraLoi. */
async function goi(method, path, data) {
  const user = await signIn()
  if (!user) return { ok: false, message: t('status.redirecting') }
  const [url, init] = yeuCau(user.access_token, method, path, data)
  try {
    const res = await fetch(url, init)
    return docTraLoi(res.status, docThan(await res.text()))
  } catch {
    return { ok: false, message: t(LOI.mang) }
  }
}

// --- thông báo: tin thường đọc lịch sự (role=status), lỗi đọc ngay (role=alert). Câu là hàm để đổi ngôn ngữ thì
// viết lại; câu báo của một lời gọi (kq.message) dựng lúc nhận trả lời, theo ngôn ngữ lúc đó ---
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

// --- chuyển phần ---
const PHAN = ['gui-don', 'don-cua-toi', 'viec-can-duyet']
let phanHien = 'gui-don'

function moPhan(ten, { focus = true } = {}) {
  phanHien = ten
  for (const p of PHAN) {
    el(p).hidden = p !== ten
    const tab = document.querySelector(`[data-phan="${p}"]`)
    if (p === ten) tab.setAttribute('aria-current', 'true')
    else tab.removeAttribute('aria-current')
  }
  capNhatViec()
  if (focus) el(`tieu-de-${ten}`).focus()
}

/** Số ngày nghỉ thành chữ: tiếng Anh phân biệt "1 day" với "3 days". */
const chuSoNgay = (n) => (n === 1 ? t('detail.oneDay') : t('detail.dayCount', { n }))

/** Dòng nhãn — giá trị của một đơn (dl), thêm số ngày nghỉ khi có đủ hai ngày. */
function bangDon(rows, data) {
  const dl = make('dl', { className: 'chi-tiet' })
  for (const r of rows) dl.append(make('dt', { textContent: r.label }), make('dd', { textContent: r.value }))
  const n = soNgay(data?.tuNgay, data?.denNgay)
  if (n) dl.append(make('dt', { textContent: t('detail.days') }), make('dd', { textContent: chuSoNgay(n) }))
  return dl
}

// --- Đơn của tôi: tải theo trang (#325). Lượt đầu và lượt làm mới tải trang đầu; đã bấm "Xem thêm" thì ghép trang
// đầu vào, giữ các đơn cũ hơn đã tải ---
async function taiDon(forms) {
  const kq = await goi('GET', duong.donCuaToi(0))
  if (!kq.ok) {
    baoLoi(() => t('error.loadMine', { error: kq.message }))
    return
  }
  const trang = Array.isArray(kq.data) ? kq.data : []
  if (view.xemThem) view.don = ghepDon(view.don, trang)
  else {
    view.don = sapXepDon(trang)
    view.tiep = conTrang(trang) ? TRANG : null
  }
  veDon(forms)
}

let dangXemThem = false
async function xemThem(forms) {
  if (dangXemThem || view.tiep === null) return
  dangXemThem = true
  el('xem-them-don').setAttribute('aria-disabled', 'true')
  try {
    const tu = view.tiep
    const kq = await goi('GET', duong.donCuaToi(tu))
    if (!kq.ok) {
      baoLoi(() => t('error.loadMine', { error: kq.message }))
      return
    }
    const trang = Array.isArray(kq.data) ? kq.data : []
    const daCo = new Set(view.don.map((d) => d.id))
    view.don = ghepDon(view.don, trang)
    view.xemThem += 1
    view.tiep = conTrang(trang) ? tu + TRANG : null
    veDon(forms)
    const moi = view.don.filter((d) => !daCo.has(d.id))
    baoTin(() => (moi.length ? t('mine.loadedMore', { n: moi.length }) : t('mine.noMore')))
    // tiêu điểm tới đơn đầu tiên vừa tải: nút Xem thêm có thể vừa ẩn, người dùng bàn phím đọc tiếp từ đó
    if (moi.length) theDon(moi[0].id)?.focus()
    else if (view.tiep === null) el('tieu-de-don-cua-toi').focus()
  } finally {
    dangXemThem = false
    el('xem-them-don').removeAttribute('aria-disabled')
  }
}

const theDon = (id) => [...el('danh-sach-don').children].find((li) => li.dataset.id === id)

// --- Hủy đơn (#325): hỏi lại bằng hộp thoại modal, Esc hay "Không hủy" là thôi ---
function hoiHuy(don) {
  const hop = el('hoi-huy')
  el('hoi-huy-don').textContent = t('mine.sentAt', { time: ngayGio(don.startedAt) })
  hop.returnValue = ''
  return new Promise((xong) => {
    hop.addEventListener('close', () => xong(hop.returnValue === 'co'), { once: true })
    hop.showModal()
  })
}

async function huyDon(don, forms) {
  if (!(await hoiHuy(don))) return
  const kq = await goi('DELETE', duong.huyDon(don.id))
  if (!kq.ok) {
    baoLoi(() => kq.message)
    if (kq.status === 404 || kq.status === 409) await taiDon(forms)
    return
  }
  // đổi ngay mục đó (đơn có thể ở trang đã xem thêm, lượt làm mới không tải lại trang đó)
  const luc = new Date().toISOString()
  view.don = view.don.map((d) => (d.id === don.id ? { ...d, cancelled: true, endedAt: d.endedAt ?? luc } : d))
  veDon(forms)
  baoTin(() => t('notice.cancelled'))
  // nút Hủy vừa mất: tiêu điểm về thẻ của đơn đó
  theDon(don.id)?.focus()
}

function veDon(forms) {
  const list = view.don
  el('danh-sach-don').replaceChildren(...list.map((don) => {
    const tt = trangThai(don)
    const li = make('li', { className: 'the', tabIndex: -1 })
    li.dataset.id = don.id
    const dau = make('div', { className: 'the-dau' })
    const gui = t('mine.sentAt', { time: ngayGio(don.startedAt) })
    dau.append(make('span', { className: `nhan nhan-${tt.ma}`, textContent: tt.nhan }),
      make('span', { className: 'gio', textContent: gui }))
    li.append(dau, bangDon(tomTat(forms.don, don.data), don.data))
    if (don.endedAt) {
      const ketQua = tomTat(forms.duyet, don.data).filter((r) => don.data?.[r.name] !== undefined)
      if (ketQua.length) li.append(bangDon(ketQua))
      const time = ngayGio(don.endedAt)
      const chu = don.cancelled === true ? t('mine.cancelledAt', { time }) : t('mine.endedAt', { time })
      li.append(make('p', { className: 'gio', textContent: chu }))
    }
    if (huyDuoc(don)) {
      // nhãn đọc kèm giờ gửi: nhiều đơn đang chờ thì mỗi nút một tên khác nhau, vẫn bắt đầu bằng chữ trên nút
      const nut = make('button', { type: 'button', className: 'btn ghost', textContent: t('mine.cancel') })
      nut.setAttribute('aria-label', t('mine.cancelLabel', { time: ngayGio(don.startedAt) }))
      nut.addEventListener('click', () => huyDon(don, forms))
      const hang = make('div', { className: 'the-nut' })
      hang.append(nut)
      li.append(hang)
    }
    return li
  }))
  el('khong-co-don').hidden = list.length > 0
  // còn trang sau thì số đếm có dấu +
  el('dem-don').textContent = list.length ? `${list.length}${view.tiep === null ? '' : '+'}` : ''
  el('xem-them-don').hidden = view.tiep === null
}

// --- Việc cần duyệt: thẻ còn việc giữ nguyên khi làm mới, để không mất ghi chú đang gõ. Mỗi việc: {task, li, form} ---
const theViec = new Map()
let soThe = 0

function dungTheViec(task, forms, draft) {
  const li = make('li', { className: 'the' })
  const h2 = make('h2', { textContent: t('review.sentAt', { time: ngayGio(task.createdAt) }) })
  h2.tabIndex = -1
  li.append(h2)
  // người duyệt cần biết đơn của ai (#506); lõi không trả tên thì bỏ dòng
  const name = nguoiGui(task)
  if (name) li.append(make('p', { className: 'gio', textContent: t('review.from', { name }) }))
  li.append(bangDon(tomTat(forms.don, task.data), task.data))
  if (task.dueAt) {
    li.append(make('p', { className: 'gio', textContent: t('review.due', { time: ngayGio(task.dueAt) }) }))
  }
  const khung = make('div', { className: 'khung-form' })
  li.append(khung)
  const the = { task, li, form: null }
  // formKey lạ (quy trình đổi mà trang chưa tải lại): không đoán mẫu nào, báo trên thẻ
  if (!Object.hasOwn(forms.byKey, task.formKey)) {
    khung.append(make('p', { className: 'loi', textContent: t('review.unknownForm', { formKey: task.formKey }) }))
    return the
  }
  the.form = veForm(khung, forms.byKey[task.formKey], {
    idPrefix: `viec-${++soThe}-`,
    submitLabel: t('review.submit'),
    draft,
    onSubmit: async (data) => {
      const kq = await goi('POST', duong.xongViec(task.id), data)
      if (kq.errors) {
        // thẻ có thể vừa được vẽ lại (đổi ngôn ngữ lúc đang gửi): báo vào form đang hiện của việc này
        theViec.get(task.id)?.form?.setErrors(kq.errors)
        return
      }
      if (!kq.ok) {
        baoLoi(() => kq.message)
        if (kq.status === 404 || kq.status === 409) await taiViec(forms)
        return
      }
      boTheViec(task.id)
      baoTin(() => (data.quyetDinh === 'tu-choi' ? t('notice.declined') : t('notice.approved')))
      capNhatViec()
      const tiep = el('danh-sach-viec').querySelector('h2')
      ;(tiep || el('tieu-de-viec-can-duyet')).focus()
    },
  })
  return the
}

function boTheViec(id) {
  theViec.get(id)?.li.remove()
  theViec.delete(id)
}

function capNhatViec() {
  const n = theViec.size
  el('khong-co-viec').hidden = n > 0
  el('dem-viec').textContent = n ? String(n) : ''
  // chỉ người có việc mới thấy phần này; đang đứng ở đó thì giữ lại để đọc câu "không còn đơn"
  document.querySelector('[data-phan="viec-can-duyet"]').hidden = n === 0 && phanHien !== 'viec-can-duyet'
}

async function taiViec(forms) {
  const kq = await goi('GET', duong.viec())
  if (!kq.ok) {
    baoLoi(() => t('error.loadReview', { error: kq.message }))
    return
  }
  const { them, bo } = doiChieu([...theViec.keys()], Array.isArray(kq.data) ? kq.data : [])
  for (const id of bo) boTheViec(id)
  for (const task of them) {
    const the = dungTheViec(task, forms)
    theViec.set(task.id, the)
    el('danh-sach-viec').append(the.li)
  }
  capNhatViec()
}

// --- Gửi đơn ---
function veFormDon(forms, draft) {
  return veForm(el('form-don'), forms.don, {
    idPrefix: 'don-',
    submitLabel: t('request.submit'),
    draft,
    onSubmit: async (data) => {
      // view.formDon, không phải form lúc dựng: đổi ngôn ngữ lúc đang gửi thì form đã được vẽ lại
      const kq = await goi('POST', duong.guiDon(), data)
      if (kq.errors) {
        view.formDon.setErrors(kq.errors)
        return
      }
      if (!kq.ok) {
        baoLoi(() => t('error.sendFailed', { error: kq.message }))
        return
      }
      view.formDon.reset()
      const n = soNgay(data.tuNgay, data.denNgay)
      baoTin(() => (n ? t('notice.sentDays', { days: chuSoNgay(n) }) : t('notice.sent')))
      await taiDon(forms)
    },
  })
}

async function napForm(formKey) {
  const kq = await goi('GET', duong.form(formKey))
  if (!kq.ok || !kq.data || typeof kq.data !== 'object') throw new Error(kq.message || t('error.emptyForm'))
  return kq.data
}

/** Nút đổi ngôn ngữ: lưu lựa chọn (chung với Văn phòng điện tử), gán lại phần tĩnh rồi vẽ lại phần đang hiện; form
 *  dựng lại theo ngôn ngữ mới, giữ chữ đang gõ (draft). */
function switchLocale() {
  saveLocale(setLocale(locale() === 'vi' ? 'en' : 'vi'))
  localize(document)
  el('nguoi').textContent = view.nguoi()
  thongBao()
  const forms = view.forms
  if (!forms) return
  view.formDon = veFormDon(forms, view.formDon.values())
  if (view.don) veDon(forms)
  for (const [id, cu] of theViec) {
    const moi = dungTheViec(cu.task, forms, cu.form?.values())
    cu.li.replaceWith(moi.li)
    theViec.set(id, moi)
  }
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

  let forms
  try {
    const [don, duyet] = await Promise.all([napForm(FORM_DON), napForm(FORM_DUYET)])
    forms = { don, duyet, byKey: { [FORM_DON]: don, [FORM_DUYET]: duyet } }
    view.formDon = veFormDon(forms)       // mountForm ném lỗi khi schema không dùng được: báo như không nạp được mẫu
  } catch (err) {
    baoLoi(() => t('error.loadForms', { error: err.message }))
    return
  }
  view.forms = forms
  baoTin(() => '')
  el('ung-dung').hidden = false
  for (const p of PHAN) {
    document.querySelector(`[data-phan="${p}"]`).addEventListener('click', () => moPhan(p))
  }
  moPhan('gui-don', { focus: false })
  el('xem-them-don').addEventListener('click', () => xemThem(forms))
  // một lượt tải lại mỗi lúc: lượt trước chậm quá LAM_MOI_MS thì lượt sau dùng chung, không chồng kết quả cũ lên mới
  let dangTai = null
  const lamMoi = () => (dangTai ??= Promise.all([taiDon(forms), taiViec(forms)])
    .catch((err) => baoLoi(() => t('error.reload', { error: err.message })))
    .finally(() => { dangTai = null }))
  await lamMoi()
  setInterval(lamMoi, LAM_MOI_MS)
}

main()
