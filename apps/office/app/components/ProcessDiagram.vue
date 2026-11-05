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
import { FONT, LINE_H, diagramView } from '~/utils/processDiagram'
import type { DocumentProcess, StepState } from '~/utils/processDiagram'

// Sơ đồ quy trình của văn bản (#603), SVG tự vẽ theo khuôn trang Cảm biến (cam-bien.vue): vùng cuộn ngang nhận tiêu
// điểm để cuộn bằng phím, <svg role="img">, mỗi phần tử một <g> có <title>; hình học ở utils/processDiagram.ts. Sơ đồ
// giữ đúng cỡ của DI (chữ 12px), không co theo cột. Ba trạng thái khác nhau cả ở nét (liền, dày, đứt) chứ không chỉ ở
// màu; danh sách bước dạng chữ ở dưới cho trình đọc màn hình.
const props = defineProps<{ diagram: DocumentProcess; titleId: string }>()
const { t } = useI18n()
const view = computed(() => diagramView(props.diagram))

const TONE: Record<StepState, { shape: string; text: string; width: number; dash?: string }> = {
  done: { shape: 'fill-brand-50 stroke-brand-600', text: 'fill-stone-900', width: 2 },
  active: { shape: 'fill-amber-100 stroke-amber-800', text: 'fill-stone-900 font-semibold', width: 3.5 },
  '': { shape: 'fill-white stroke-stone-400', text: 'fill-stone-600', width: 1.25, dash: '5 4' },
}
const LEGEND: StepState[] = ['done', 'active', '']
// viền trắng quanh chữ: chữ nằm cạnh hay đè lên đường vẫn đọc được
const HALO = { 'stroke-width': 3, 'stroke-linejoin': 'round', 'paint-order': 'stroke' } as const
const STATE_KEY = { done: 'done', active: 'active', '': 'todo' } as const
const stateText = (s: StepState) => t(`doc.process.${STATE_KEY[s]}`)
</script>

<template>
  <div class="space-y-4" data-testid="process-diagram" :data-key="diagram.key">
    <div
      class="overflow-x-auto rounded-lg border border-stone-200 bg-white" tabindex="0" role="region"
      :aria-labelledby="titleId" data-testid="process-scroll"
    >
      <svg
        :viewBox="view.viewBox" :width="view.width" :height="view.height" class="block max-w-none" role="img"
        :aria-label="t('doc.process.label')"
      >
        <defs>
          <marker
            id="process-arrow-done" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M0 0 10 5 0 10Z" class="fill-brand-600" />
          </marker>
          <marker
            id="process-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M0 0 10 5 0 10Z" class="fill-stone-400" />
          </marker>
        </defs>
        <!-- đường vẽ trước để mũi tên nằm dưới mép hình -->
        <g v-for="e in view.edges" :key="e.id" :data-testid="`edge-${e.id}`" :data-state="e.state">
          <path
            :d="e.d" fill="none" stroke-linejoin="round" :stroke-width="e.state === 'done' ? 2 : 1.25"
            :class="e.state === 'done' ? 'stroke-brand-600' : 'stroke-stone-400'"
            :marker-end="`url(#process-arrow${e.state === 'done' ? '-done' : ''})`"
          />
          <text
            v-if="e.label" :x="e.label.x" :y="e.label.y" :text-anchor="e.label.anchor" :font-size="FONT - 1"
            class="fill-stone-600 stroke-white" v-bind="HALO"
          >
            <tspan v-for="(line, i) in e.label.lines" :key="i" :x="e.label.x" :dy="i ? LINE_H : 0">{{ line }}</tspan>
          </text>
        </g>
        <g
          v-for="s in view.shapes" :key="s.id" :data-testid="`node-${s.id}`" :data-state="s.state"
          :data-kind="s.kind"
        >
          <title>{{ s.name }} — {{ stateText(s.state) }}</title>
          <rect
            v-if="s.shape === 'rect'" :x="s.x" :y="s.y" :width="s.w" :height="s.h" rx="10"
            :class="TONE[s.state].shape" :stroke-width="TONE[s.state].width" :stroke-dasharray="TONE[s.state].dash"
          />
          <template v-else-if="s.shape === 'circle'">
            <circle
              :cx="s.cx" :cy="s.cy" :r="s.r" :class="TONE[s.state].shape"
              :stroke-width="TONE[s.state].width + (s.ring === 'thick' ? 1.5 : 0)"
              :stroke-dasharray="TONE[s.state].dash"
            />
            <circle
              v-if="s.ring === 'double'" :cx="s.cx" :cy="s.cy" :r="s.r - 4" :class="TONE[s.state].shape"
              stroke-width="1.25"
            />
          </template>
          <template v-else>
            <polygon
              :points="s.points" :class="TONE[s.state].shape" :stroke-width="TONE[s.state].width"
              :stroke-dasharray="TONE[s.state].dash"
            />
            <path
              v-if="s.mark" :d="s.mark" fill="none" class="stroke-stone-700" stroke-width="2.5"
              stroke-linecap="round"
            />
          </template>
          <text
            v-if="s.label.lines.length" :x="s.label.x" :y="s.label.y" :text-anchor="s.label.anchor"
            :font-size="FONT" :class="[TONE[s.state].text, 'stroke-white']" v-bind="HALO"
          >
            <tspan v-for="(line, i) in s.label.lines" :key="i" :x="s.label.x" :dy="i ? LINE_H : 0">{{ line }}</tspan>
          </text>
        </g>
      </svg>
    </div>

    <ul class="flex flex-wrap gap-x-5 gap-y-2 text-sm text-stone-700" data-testid="process-legend">
      <li v-for="s in LEGEND" :key="s" class="flex items-center gap-2">
        <svg class="h-4 w-6 shrink-0" viewBox="0 0 24 16" aria-hidden="true">
          <rect
            x="2" y="2" width="20" height="12" rx="4" :class="TONE[s].shape"
            :stroke-width="Math.min(TONE[s].width, 2.5)" :stroke-dasharray="s ? undefined : '3 2'"
          />
        </svg>
        {{ stateText(s) }}
      </li>
    </ul>

    <div>
      <p :id="`${titleId}-steps`" class="text-sm font-semibold text-stone-900">{{ t('doc.process.steps') }}</p>
      <ol class="mt-2 list-decimal space-y-1 pl-5 text-sm" :aria-labelledby="`${titleId}-steps`">
        <li v-for="s in view.steps" :key="s.id" :data-testid="`step-${s.id}`" :data-state="s.state">
          <span class="text-stone-900" :class="{ 'font-semibold': s.state === 'active' }">{{ s.name }}</span>
          <span class="text-stone-500"> — {{ stateText(s.state) }}</span>
        </li>
      </ol>
    </div>
  </div>
</template>
