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

import { readFileSync } from 'node:fs'

import AxeBuilder from '@axe-core/playwright'
import { expect, type Locator, type Page, test } from '@playwright/test'
import { AXE_TAGS, PASSWORD, SCAN_TIMEOUT, shot, signIn, textPdf } from './helpers'

// Hủy đơn nghỉ phép (#325) trên trình duyệt thật: gửi một đơn rồi hủy qua hộp thoại hỏi lại. DELETE đi qua cổng APISIX
// tới API quy trình chung của lõi; "Không hủy" giữ đơn, tiêu điểm về nút vừa bấm; hủy xong đơn thành "Đã hủy", tải lại
// trang vẫn vậy. Quét trợ năng khi hộp thoại đang mở. Ứng dụng cắm bằng manifest: job e2e của CI cài trước make seed.

const tag = Math.random().toString(36).slice(2, 7).toUpperCase()

// ngày nghỉ trong tương lai theo giờ Việt Nam, YYYY-MM-DD
const ngay = (sau: number) => new Date(Date.now() + 7 * 3600_000 + sau * 86400_000).toISOString().slice(0, 10)

test('hủy đơn đang chờ: hỏi lại, "Không hủy" giữ đơn, "Hủy đơn" đổi thành Đã hủy', async ({ browser }) => {
  test.skip(!PASSWORD, 'đặt MOC_DEMO_PASSWORD (make e2e tự đọc từ .env)')
  const page = await signIn(browser, 'giangvienktpm')
  const installed = (await (await page.request.get('/nghi-phep/')).text()).includes('id="form-don"')
  if (!installed) {
    expect(process.env.CI, 'CI phải cài Đơn nghỉ phép trước make e2e (ci.yml, bước make app-install)').toBeFalsy()
    test.skip(true, 'chưa cài: make app-install APP=apps/nghi-phep/app.yaml')
  }
  await page.goto('/nghi-phep/')
  const form = page.locator('#form-don form')
  await expect(form).toBeVisible()
  const lyDo = `Thử hủy đơn ${tag}`
  await page.locator('#don-loai').selectOption({ index: 1 })
  await page.locator('#don-tuNgay').fill(ngay(30))
  await page.locator('#don-denNgay').fill(ngay(30))
  // form dựng từ schema của lõi: bản có số ngày làm việc nghỉ (#325 b) thì điền 1, dưới ngưỡng Hiệu trưởng duyệt
  const soNgayLam = page.locator('#don-soNgayLam')
  if (await soNgayLam.count()) await soNgayLam.fill('1')
  await page.locator('#don-lyDo').fill(lyDo)
  await form.getByRole('button', { name: 'Gửi đơn' }).click()
  await expect(page.locator('#tin')).toContainText('Đã gửi đơn')

  await page.locator('[data-phan="don-cua-toi"]').click()
  const card = page.locator('#danh-sach-don li').filter({ hasText: lyDo })
  // "Chờ trưởng phòng duyệt", hay "Đang chờ duyệt" từ khi đơn có thể chờ Hiệu trưởng (#325 b)
  const cho = /[Cc]hờ (trưởng phòng )?duyệt/
  await expect(card).toContainText(cho)
  // mỗi nút Hủy đọc kèm giờ gửi, bắt đầu bằng chữ trên nút
  const cancel = card.getByRole('button', { name: /^Hủy đơn gửi lúc \d{2}\/\d{2}\/\d{4} \d{2}:\d{2}$/ })
  await cancel.click()
  const dialog = page.getByRole('dialog', { name: 'Hủy đơn này?' })
  await expect(dialog).toBeVisible()
  await expect(dialog.getByRole('button', { name: 'Không hủy' })).toBeFocused()

  await page.emulateMedia({ reducedMotion: 'reduce' })
  const { violations } = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze()
  expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`)).toEqual([])
  await shot(page, 'nghi-phep-hoi-huy')

  await dialog.getByRole('button', { name: 'Không hủy' }).click()
  await expect(dialog).toBeHidden()
  await expect(cancel).toBeFocused()
  await expect(card).toContainText(cho)

  await cancel.click()
  const [deleted] = await Promise.all([
    page.waitForResponse((r) => r.request().method() === 'DELETE' && r.url().includes('/api/workflow/nghi-phep/')),
    dialog.getByRole('button', { name: 'Hủy đơn' }).click(),
  ])
  expect(deleted.status()).toBe(204)
  await expect(card).toContainText('Đã hủy')
  await expect(card.getByRole('button')).toHaveCount(0)
  await expect(card).toBeFocused()
  await expect(page.locator('#tin')).toHaveText('Đã hủy đơn.')

  // lõi giữ trạng thái đã hủy: tải lại trang, đơn vẫn "Đã hủy", không còn nút Hủy
  await page.reload()
  await page.locator('[data-phan="don-cua-toi"]').click()
  await expect(card).toContainText('Đã hủy')
  await expect(card).toContainText('Hủy lúc')
  await expect(card.getByRole('button')).toHaveCount(0)
})

// Tệp đính kèm (#325 e): chọn PDF thì ô tệp tải lên /api/files ngay (ClamAV quét), đơn gửi id tệp; "Đơn của tôi" hiện
// tên tệp, nút tải về lấy tệp qua đường tải tệp của lõi, đúng từng byte. Đơn hủy rồi tệp vẫn còn, vẫn tải được.
test('đơn kèm giấy tờ: tải lên lúc chọn, thẻ đơn có tên tệp, tải về đúng byte, cả khi đã hủy', async ({ browser }) => {
  test.skip(!PASSWORD, 'đặt MOC_DEMO_PASSWORD (make e2e tự đọc từ .env)')
  const page = await signIn(browser, 'giangvienktpm')
  if (!(await page.request.get('/nghi-phep/').then((r) => r.text())).includes('id="form-don"')) {
    expect(process.env.CI, 'CI phải cài Đơn nghỉ phép trước make e2e (ci.yml, bước make app-install)').toBeFalsy()
    test.skip(true, 'chưa cài: make app-install APP=apps/nghi-phep/app.yaml')
  }
  await page.goto('/nghi-phep/')
  const form = page.locator('#form-don form')
  await expect(form).toBeVisible()
  const lyDo = `Nghỉ ốm kèm giấy ${tag}`
  const name = `giay-kham-${tag}.pdf`
  const content = textPdf('Giay kham benh', `Ma thu ${tag}`)
  await page.locator('#don-loai').selectOption({ label: 'Nghỉ ốm' })
  await page.locator('#don-tuNgay').fill(ngay(31))
  await page.locator('#don-denNgay').fill(ngay(31))
  await page.locator('#don-soNgayLam').fill('1')
  await page.locator('#don-lyDo').fill(lyDo)
  await page.locator('#don-giayTo').setInputFiles({ name, mimeType: 'application/pdf', buffer: content })
  await expect(page.locator('#don-giayTo-file')).toHaveText(`Đã tải lên «${name}»`, { timeout: SCAN_TIMEOUT })
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const { violations } = await new AxeBuilder({ page }).withTags(AXE_TAGS).analyze()
  expect(violations.map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(' | ')}`)).toEqual([])
  await shot(page, 'nghi-phep-giay-to')
  await form.getByRole('button', { name: 'Gửi đơn' }).click()
  await expect(page.locator('#tin')).toContainText('Đã gửi đơn')

  await page.locator('[data-phan="don-cua-toi"]').click()
  const card = page.locator('#danh-sach-don li').filter({ hasText: lyDo })
  await expect(card).toContainText(name)
  await taiVe(page, card.getByRole('button', { name: `Tải về ${name}` }), name, content)

  // hủy đơn: tệp ở lại, người gửi vẫn tải về được
  await card.getByRole('button', { name: /^Hủy đơn gửi lúc / }).click()
  await page.getByRole('dialog', { name: 'Hủy đơn này?' }).getByRole('button', { name: 'Hủy đơn' }).click()
  await expect(card).toContainText('Đã hủy')
  await taiVe(page, card.getByRole('button', { name: `Tải về ${name}` }), name, content)
})

async function taiVe(page: Page, button: Locator, name: string, content: Buffer) {
  const [download] = await Promise.all([page.waitForEvent('download'), button.click()])
  expect(download.suggestedFilename()).toBe(name)
  expect(readFileSync(await download.path()).equals(content)).toBe(true)
}
