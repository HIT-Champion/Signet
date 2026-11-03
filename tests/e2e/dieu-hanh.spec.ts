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

import { expect, test, type Locator } from '@playwright/test'
import { PASSWORD, TOTP_SECRET, shot, signIn } from './helpers'

// Dashboard điều hành (F3.11) trên giao diện: lãnh đạo khoa thấy số liệu văn bản của đơn vị kèm biểu đồ ECharts;
// văn thư không có mục này, mở thẳng đường dẫn cũng không thấy số liệu. Không giả định dữ liệu có sẵn: chỉ kiểm
// các con số khớp nhau giữa thẻ tổng và bảng.

async function cell(table: Locator, row: string): Promise<number> {
  return Number(await table.locator('tr', { hasText: row }).locator('td').last().innerText())
}

test('dashboard điều hành: chỉ lãnh đạo đơn vị xem, số liệu khớp giữa thẻ và bảng', async ({ browser }) => {
  test.skip(!PASSWORD || !TOTP_SECRET, 'đặt MOC_DEMO_PASSWORD, MOC_DEMO_TOTP_SECRET (make e2e tự đọc từ .env)')

  const director = await signIn(browser, 'truongkhoa', { otp: true })
  await director.getByRole('link', { name: 'Điều hành' }).click()
  await expect(director.getByRole('heading', { level: 1, name: 'Điều hành' })).toBeVisible()

  const status = director.getByTestId('board-status')
  await expect(status.locator('svg').first()).toBeVisible()       // biểu đồ ECharts đã vẽ
  const open = await cell(status, 'Chờ vào sổ') + await cell(status, 'Chờ chỉ đạo') + await cell(status, 'Đang xử lý')
  await expect(director.getByTestId('kpi-open')).toHaveText(String(open))
  // mỗi phòng của đơn vị một dòng, kể cả phòng chưa có việc
  await expect(director.getByTestId('board-departments').locator('tbody tr').first()).toBeVisible()
  await expect(director.getByTestId('board-outgoing').locator('svg').first()).toBeVisible()
  // ảnh này dùng trong README: đợi các thông báo realtime (tự tắt sau 8 giây) tắt hết để không che bảng; chỉ để ảnh
  // gọn, hết giờ vẫn chụp chứ không làm test đỏ
  await director.getByTestId('realtime-notice').first().waitFor({ state: 'detached', timeout: 15_000 }).catch(() => {})
  await shot(director, '18-dieu-hanh')

  // chọn kỳ (#529): hai bảng theo tháng không quá số tháng đã chọn, kỳ ghi trên đường dẫn
  await director.getByTestId('board-period').selectOption('3')
  await expect(director).toHaveURL(/[?&]thang=3\b/)
  await expect(director.getByTestId('board-kpis')).toContainText(/3 tháng gần nhất|Chưa có văn bản nào xử lý xong/)
  for (const id of ['board-processing', 'board-outgoing']) {
    expect(await director.getByTestId(id).locator('tbody tr').count()).toBeLessThanOrEqual(3)
  }

  // ô Quá hạn → tab Quá hạn của Văn bản đến (#529), cùng định nghĩa: số ở ô bằng số dòng không hạn chế (ô không tính
  // văn bản hạn chế); bảng theo phòng chỉ tính văn bản đang xử lý nên tổng cột Quá hạn không vượt ô
  const overdue = Number(await director.getByTestId('kpi-overdue').innerText())
  let late = 0
  for (const row of await director.getByTestId('board-departments').locator('tbody tr').all()) {
    late += Number(await row.locator('td').last().innerText())
  }
  expect(late).toBeLessThanOrEqual(overdue)
  await director.getByTestId('kpi-overdue-list').click()
  await expect(director).toHaveURL(/\/van-ban-den\?tab=overdue$/)
  await expect(director.getByRole('tab', { name: 'Quá hạn' })).toHaveAttribute('aria-selected', 'true')
  await expect(director.getByTestId('overdue-hint')).toBeVisible()
  await expect(director.locator('.moc-incoming-table, .moc-empty').first()).toBeVisible()
  const rows = director.locator('.moc-incoming-table tbody tr')
  const more = director.getByTestId('list-more')
  while (await more.isVisible()) {   // tải hết các trang rồi mới đếm
    const shown = await rows.count()
    await more.click()
    await expect.poll(() => rows.count()).toBeGreaterThan(shown)
  }
  await expect(rows.filter({ hasNot: director.getByText('Hạn chế', { exact: true }) })).toHaveCount(overdue)

  const clerk = await signIn(browser, 'vanthu', { otp: true })
  await expect(clerk.getByRole('link', { name: 'Sổ đăng ký' })).toBeVisible()
  await expect(clerk.getByRole('link', { name: 'Điều hành' })).toHaveCount(0)
  await clerk.goto('/dieu-hanh')
  await expect(clerk.getByText('Chỉ lãnh đạo đơn vị xem được trang này.')).toBeVisible()
  await expect(clerk.getByTestId('board-kpis')).toHaveCount(0)
})
