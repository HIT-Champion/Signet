<!--
  Copyright 2026 Signet Team

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

      http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.

  SPDX-License-Identifier: Apache-2.0
-->

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

// Phần "Chốt kỳ" của trang Điều hành (#542): lãnh đạo đơn vị chốt một tháng đã qua. office.close_period chép số của
// bốn khung nhìn dashboard vào office.period_closes (không sửa, không xóa được) và ghi mã băm vào sổ kiểm toán
// (migration 1792281604300). Văn bản đến chưa xong, quá hạn là số tại lúc chốt; xong trong kỳ, văn bản đi là số
// của đúng tháng đó. Hasura lọc theo đơn vị trong token, vai trò khác bị từ chối.

interface Closed {
  period: string
  closed_at: string
  sha256: string
  figures: {
    counts: { restricted: boolean; status: string | null; overdue: boolean | null; documents: number }[]
    processing: { documents: number; with_due: number; on_time: number } | null
    outgoing: { documents: number } | null
  }
}

const CLOSES = '{ office_period_closes(order_by: {period: desc}) { period closed_at sha256 figures } }'
const CLOSE = 'mutation ($period: date!) { office_close_period(args: {period: $period}) { period } }'
const OPEN = new Set(['received', 'registered', 'in_progress'])

const { t } = useI18n()
const { gql } = useApi()
const notice = useNotice()
const rows = ref<Closed[]>([])
const loaded = ref(false)
const failure = ref('')
const busy = ref(false)
const picked = ref('')

async function load() {
  failure.value = ''
  try {
    rows.value = (await gql<{ office_period_closes: Closed[] }>(CLOSES)).office_period_closes
    loaded.value = true
  } catch (e) {
    failure.value = errorText(t, e)
  }
}
onMounted(load)

// 12 tháng đã qua gần nhất theo giờ Việt Nam, bỏ tháng đã chốt
const choices = computed(() => {
  const [y, m] = today().split('-').map(Number) as [number, number]
  const closed = new Set(rows.value.map((r) => r.period))
  return Array.from({ length: 12 }, (_, i) => {
    const d = new Date(y, m - 2 - i, 1)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-01`
  }).filter((p) => !closed.has(p))
})
watch(choices, (c) => {
  if (!c.includes(picked.value)) picked.value = c[0] ?? ''
}, { immediate: true })

// như nhãn tháng của các biểu đồ trên trang: 10/2026
function month(iso: string) {
  const [y, m] = iso.split('-')
  return `${Number(m)}/${y}`
}

async function close() {
  if (!picked.value || !confirm(t('periodClose.confirm', { month: month(picked.value) }))) return
  busy.value = true
  try {
    await gql(CLOSE, { period: picked.value })
    notice.ok(t('periodClose.closed', { month: month(picked.value) }))
    await load()
  } catch (e) {
    notice.error(errorText(t, e))
  } finally {
    busy.value = false
  }
}

const table = computed(() => rows.value.map((r) => {
  const counts = r.figures.counts.filter((c) => !c.restricted)
  const p = r.figures.processing
  return {
    period: r.period,
    closedAt: fmtDateTime(r.closed_at),
    open: counts.filter((c) => OPEN.has(c.status ?? '')).reduce((n, c) => n + c.documents, 0),
    overdue: counts.filter((c) => c.overdue).reduce((n, c) => n + c.documents, 0),
    done: p?.documents ?? 0,
    onTime: p?.with_due ? `${p.on_time}/${p.with_due}` : '—',
    issued: r.figures.outgoing?.documents ?? 0,
    sha256: r.sha256.replace(/^\\x/, ''),
  }
}))
</script>

<template>
  <section class="card p-4" data-testid="period-close" aria-labelledby="period-close-title">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="min-w-0 max-w-2xl">
        <h2 id="period-close-title" class="font-medium text-stone-900">{{ t('periodClose.title') }}</h2>
        <p class="mt-1 text-xs text-stone-500">{{ t('periodClose.hint') }}</p>
      </div>
      <div v-if="loaded && choices.length" class="flex shrink-0 items-center gap-2">
        <label class="sr-only" for="period-close-month">{{ t('periodClose.month') }}</label>
        <select id="period-close-month" v-model="picked" class="input w-auto" data-testid="period-close-month">
          <option v-for="p in choices" :key="p" :value="p">{{ month(p) }}</option>
        </select>
        <button
          type="button" class="btn-primary" :disabled="busy || !picked" data-testid="period-close-submit"
          @click="close"
        >
          {{ t('periodClose.submit') }}
        </button>
      </div>
    </div>

    <p v-if="failure" class="mt-4 text-sm text-red-700">{{ failure }}</p>
    <p v-else-if="!loaded" class="mt-4 text-sm text-stone-500">{{ t('app.loading') }}</p>
    <p v-else-if="!table.length" class="mt-4 text-sm text-stone-500" data-testid="period-close-empty">
      {{ t('periodClose.empty') }}
    </p>
    <div v-else class="moc-table-scroll mt-4" tabindex="0" role="region" :aria-label="t('periodClose.title')">
      <table class="moc-table" data-testid="period-close-list">
        <thead>
          <tr>
            <th>{{ t('periodClose.period') }}</th>
            <th>{{ t('periodClose.closedAt') }}</th>
            <th class="text-right">{{ t('periodClose.open') }}</th>
            <th class="text-right">{{ t('periodClose.overdue') }}</th>
            <th class="text-right">{{ t('periodClose.done') }}</th>
            <th class="text-right">{{ t('board.onTime') }}</th>
            <th class="text-right">{{ t('board.issued') }}</th>
            <th>{{ t('periodClose.sha256') }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in table" :key="r.period" :data-period="r.period">
            <td class="text-stone-700">{{ month(r.period) }}</td>
            <td class="text-stone-700">{{ r.closedAt }}</td>
            <td class="text-right">{{ r.open }}</td>
            <td class="text-right">{{ r.overdue }}</td>
            <td class="text-right">{{ r.done }}</td>
            <td class="text-right">{{ r.onTime }}</td>
            <td class="text-right">{{ r.issued }}</td>
            <td><code class="text-xs" :title="r.sha256">{{ r.sha256.slice(0, 12) }}…</code></td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>
