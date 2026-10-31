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
// Nhịp chờ của trợ lý dựng từ biểu tượng Liền mạch (public/brand/README.md: hai nét cùng màu, chỉ co giãn đều, không
// bóng). trace: biểu tượng mờ làm nền, một đoạn sáng chạy dọc hai nét (đang tìm). breathe: cả biểu tượng co giãn và
// nhạt theo nhịp thở (đang soạn); stamp: ấn dấu một lần khi khối hiện ra rồi mới thở. Chữ trạng thái (slot) có vệt
// sáng lướt qua. Máy bật giảm chuyển động: biểu tượng đứng yên, chữ không lấp lánh
defineProps<{ motion: 'trace' | 'breathe'; stamp?: boolean }>()
</script>

<template>
  <span class="wait-mark" :class="[`wait-mark--${motion}`, { 'wait-mark--stamp': stamp }]">
    <svg class="text-brand-700" viewBox="0 0 64 64" aria-hidden="true">
      <circle v-if="stamp" class="wait-mark-ring" cx="32" cy="32" r="30" />
      <g class="wait-mark-base">
        <path d="M45 10H26c-9 0-16 7-16 16s7 16 16 16h12" />
        <path d="M19 54h19c9 0 16-7 16-16s-7-16-16-16H26" />
      </g>
      <g class="wait-mark-ink">
        <path pathLength="100" d="M45 10H26c-9 0-16 7-16 16s7 16 16 16h12" />
        <path pathLength="100" d="M19 54h19c9 0 16-7 16-16s-7-16-16-16H26" />
      </g>
    </svg>
    <span v-if="$slots.default" class="wait-mark-label"><slot /></span>
  </span>
</template>

<style scoped>
.wait-mark { display: inline-flex; align-items: center; gap: 10px; }
.wait-mark svg { flex: none; width: 24px; height: 24px; overflow: visible; }
.wait-mark path { fill: none; stroke: currentColor; stroke-width: 9; stroke-linecap: round; }
.wait-mark-base path { opacity: 0; }
.wait-mark-ink { transform-origin: 32px 32px; }
.wait-mark-ring { fill: none; stroke: currentColor; stroke-width: 2; opacity: 0; transform-origin: 32px 32px; }

@media (prefers-reduced-motion: no-preference) {
  .wait-mark--trace .wait-mark-base path { opacity: 0.2; }
  .wait-mark--trace .wait-mark-ink path { stroke-dasharray: 22 78; animation: wait-mark-trace 1.5s linear infinite; }
  .wait-mark--trace .wait-mark-ink path + path { animation-delay: -0.75s; }
  .wait-mark--breathe .wait-mark-ink { animation: wait-mark-breathe 1.8s ease-in-out infinite; }
  .wait-mark--stamp .wait-mark-ink {
    animation:
      wait-mark-stamp 0.9s cubic-bezier(0.45, 0, 0.2, 1) both,
      wait-mark-breathe 1.8s ease-in-out 0.9s infinite;
  }
  .wait-mark--stamp .wait-mark-ring { animation: wait-mark-ring 0.9s cubic-bezier(0.45, 0, 0.2, 1) both; }
  /* nền chữ là màu chữ thường (#3b4d45), vệt sáng là brand-700: cả hai đạt 4.5:1 trên nền trắng */
  .wait-mark-label {
    background: linear-gradient(100deg, #3b4d45 0 38%, #0b6b53 50%, #3b4d45 62% 100%);
    background-size: 260% 100%;
    -webkit-background-clip: text;
    background-clip: text;
    color: transparent;
    animation: wait-mark-shimmer 2.2s linear infinite;
  }
}
@media (forced-colors: active) {
  .wait-mark-label { background: none; color: CanvasText; animation: none; }
}

@keyframes wait-mark-trace { from { stroke-dashoffset: 0; } to { stroke-dashoffset: -100; } }
@keyframes wait-mark-breathe {
  0%, 100% { transform: scale(1); opacity: 1; }
  50% { transform: scale(0.9); opacity: 0.55; }
}
@keyframes wait-mark-stamp {
  0% { transform: scale(1.22); opacity: 0; }
  40% { transform: scale(0.93); opacity: 1; }
  70%, 100% { transform: scale(1); opacity: 1; }
}
@keyframes wait-mark-ring {
  0%, 30% { transform: scale(0.7); opacity: 0; }
  45% { opacity: 0.55; }
  100% { transform: scale(1.35); opacity: 0; }
}
@keyframes wait-mark-shimmer { from { background-position: 100% 0; } to { background-position: 0 0; } }
</style>
