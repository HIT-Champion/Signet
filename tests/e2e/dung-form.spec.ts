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

import AxeBuilder from '@axe-core/playwright'
import { readFileSync } from 'node:fs'
import { expect, test, type Locator, type Page } from '@playwright/test'
import { AXE_TAGS, PASSWORD, TOTP_SECRET, shot, signIn } from './helpers'

// Trình dựng form (/ung-dung/dung-form, #303 bước 1b): quản trị đơn vị mở trang từ Danh mục ứng dụng, khai một form
// ba trường (chữ, ngày không trước hôm nay, danh sách chọn), tên biến và khóa form tự suy từ nhãn; phần kiểm theo
// luật lúc cài báo đạt; xem trước bằng chính module form của ứng dụng (lib/schema-form.js): gửi trống thì ô bắt buộc
// báo lỗi, điền đủ thì ra dữ liệu sẽ gửi; tệp tải về đúng tên, đúng nội dung đang hiện. Không gọi API nào: form chỉ
// vào lõi khi cài bằng moc app install (svc-workflow kiểm lại lúc đó). Chuyên viên không có nút, mở thẳng đường dẫn
// thì thấy câu chỉ quản trị dùng được. Hai ảnh (dung-form-*) dùng cho tài liệu, chép từ artifact e2e-anh của CI.

// Ảnh cho tài liệu: khung nhìn cao bằng cả trang rồi mới chụp. Chụp toàn trang ở khung 860px thì Chrome ghép từng
// đoạn, cột phải (sticky) và thanh bên trôi xuống giữa ảnh, phần đầu ảnh mất cột kiểm, xem trước
async function shotWhole(page: Page, name: string) {
  const size = page.viewportSize()!
  const height = await page.evaluate(() => document.documentElement.scrollHeight)
  await page.setViewportSize({ width: size.width, height: Math.max(size.height, height) })
  await shot(page, name)
  await page.setViewportSize(size)
}

test('trình dựng form: khai trường, xem trước, tải tệp JSON Schema; chỉ quản trị đơn vị', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'đặt MOC_DEMO_PASSWORD, MOC_DEMO_TOTP_SECRET (make e2e tự đọc từ .env)')

  const admin = await signIn(browser, 'quantri', { otp: true })
  await admin.goto('/ung-dung')
  await admin.getByTestId('open-form-builder').click()
  await expect(admin).toHaveURL(/\/ung-dung\/dung-form\/?$/)
  await expect(admin.getByRole('heading', { level: 1, name: 'Dựng form' })).toBeVisible()
  // form trống: còn lỗi, chưa tải được, chưa có gì để xem trước
  await expect(admin.getByTestId('fb-count')).toBeVisible()
  await expect(admin.getByTestId('fb-download')).toBeDisabled()
  await expect(admin.getByTestId('form-builder-preview')).toContainText('Thêm trường để xem trước.')

  await admin.getByLabel('Tên form (tiếng Việt)').fill('Đăng ký phòng họp')
  await admin.getByLabel('Tên form (tiếng Anh)').fill('Meeting room booking')
  await admin.getByLabel('Tên ứng dụng').fill('dat-phong')

  // thêm một trường kiểu `widget`; khung sửa của trường mới tự mở
  const add = async (index: number, widget: string, vi: string, en: string): Promise<Locator> => {
    await admin.getByLabel('Kiểu ô của trường mới').selectOption(widget)
    await admin.getByTestId('fb-add').click()
    const editor = admin.getByTestId(`fb-editor-${index}`)
    await editor.getByLabel('Nhãn (tiếng Việt)', { exact: true }).fill(vi)
    await editor.getByLabel('Nhãn (tiếng Anh)', { exact: true }).fill(en)
    return editor
  }
  await add(0, 'text', 'Nội dung cuộc họp', 'Meeting topic')
  const date = await add(1, 'date', 'Ngày họp', 'Meeting date')
  await date.getByLabel('So với hôm nay').selectOption('not-before-today')
  const room = await add(2, 'select', 'Phòng', 'Room')
  await room.getByLabel('Lựa chọn 1: nhãn tiếng Việt').fill('Phòng A')
  await room.getByLabel('Lựa chọn 1: nhãn tiếng Anh').fill('Room A')
  await room.getByRole('button', { name: 'Thêm lựa chọn' }).click()
  await room.getByLabel('Lựa chọn 2: nhãn tiếng Việt').fill('Phòng B')
  await room.getByLabel('Lựa chọn 2: nhãn tiếng Anh').fill('Room B')

  // tên biến, khóa form, giá trị lựa chọn suy từ nhãn tiếng Việt, bỏ dấu
  for (const [i, name] of ['noiDungCuocHop', 'ngayHop', 'phong'].entries()) {
    await expect(admin.getByTestId(`fb-field-${i}`)).toContainText(name)
  }
  await expect(room.getByLabel('Lựa chọn 2: giá trị lưu')).toHaveValue('phong-b')
  await expect(admin.getByTestId('fb-passed')).toBeVisible()
  await expect(admin.getByTestId('fb-manifest'))
    .toHaveText('workflow:\n  forms:\n    dat-phong.dang-ky-phong-hop: forms/dang-ky-phong-hop.json\n')
  await shotWhole(admin, 'dung-form-1-cac-truong')

  // xem trước: gửi trống thì ba ô bắt buộc báo lỗi, điền đủ thì ra dữ liệu sẽ gửi
  const preview = admin.getByTestId('form-builder-preview')
  const send = preview.getByRole('button', { name: 'Gửi thử' })
  await send.click()
  for (const name of ['noiDungCuocHop', 'ngayHop', 'phong']) {
    await expect(preview.locator(`#xem-truoc-${name}`)).toHaveAttribute('aria-invalid', 'true')
  }
  await expect(admin.getByTestId('fb-sent')).toHaveCount(0)
  await preview.locator('#xem-truoc-noiDungCuocHop').fill('Họp bộ môn tháng 11')
  await preview.locator('#xem-truoc-ngayHop').fill('2030-01-15')
  // giá trị của <option> là số thứ tự lựa chọn (schema-form.js), nên chọn theo nhãn; dữ liệu gửi vẫn là giá trị lưu
  await preview.locator('#xem-truoc-phong').selectOption({ label: 'Phòng B' })
  await send.click()
  const sent = JSON.parse(await admin.getByTestId('fb-sent').locator('pre').innerText()) as Record<string, unknown>
  expect(sent).toEqual({ noiDungCuocHop: 'Họp bộ môn tháng 11', ngayHop: '2030-01-15', phong: 'phong-b' })
  await shotWhole(admin, 'dung-form-2-xem-truoc')

  // trợ năng của chính trang này (trang cần vai quản trị, tro-nang.spec.ts không quét): khung sửa đang mở, dữ liệu
  // của phần xem trước và nội dung tệp đang hiện — các khung mã cuộn được phải nhận tiêu điểm bàn phím
  await admin.getByText('Xem nội dung tệp').click()
  await expect(admin.getByTestId('fb-json')).toBeVisible()
  await admin.emulateMedia({ reducedMotion: 'reduce' })
  const { violations } = await new AxeBuilder({ page: admin }).withTags(AXE_TAGS).analyze()
  const where = (v: (typeof violations)[number]) => v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')
  expect(violations.map((v) => `${v.id}: ${v.help} — ${where(v)}`)).toEqual([])

  // tải về: tên tệp theo khóa form, nội dung đúng như phần "Xem nội dung tệp"
  const [download] = await Promise.all([admin.waitForEvent('download'), admin.getByTestId('fb-download').click()])
  expect(download.suggestedFilename()).toBe('dang-ky-phong-hop.json')
  const text = readFileSync(await download.path(), 'utf8')
  expect(text).toBe(await admin.getByTestId('fb-json').textContent())
  const schema = JSON.parse(text) as { $id: string, required: string[], properties: Record<string, unknown> }
  expect(schema.$id).toBe('urn:moc:app:dat-phong:form:dang-ky-phong-hop')
  expect(Object.keys(schema.properties)).toEqual(['noiDungCuocHop', 'ngayHop', 'phong'])
  expect(schema.required).toEqual(['noiDungCuocHop', 'ngayHop', 'phong'])

  const staff = await signIn(browser, 'chuyenviendt')
  await staff.goto('/ung-dung')
  await expect(staff.getByRole('heading', { level: 1, name: 'Danh mục ứng dụng' })).toBeVisible()
  await expect(staff.getByTestId('open-form-builder')).toHaveCount(0)
  await staff.goto('/ung-dung/dung-form')
  await expect(staff.getByTestId('form-builder-denied')).toHaveText('Chỉ quản trị đơn vị dùng trang này.')
  await expect(staff.getByTestId('fb-add')).toHaveCount(0)
})
