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
import type { Chat } from '~/utils/chatHistory'

// Lịch sử trò chuyện của trang Hỏi đáp (utils/chatHistory.ts): nút "Cuộc trò chuyện mới", nút mở danh sách các cuộc
// đã lưu trong trình duyệt này; bấm một cuộc thì mở lại, nút × xóa cuộc đó. Đang tìm hay đang viết thì không đổi cuộc.
const props = defineProps<{ chats: Chat[]; current: string; busy: boolean; hasTurns: boolean }>()
const emit = defineEmits<{ fresh: []; pick: [id: string]; remove: [id: string] }>()
const { t } = useI18n()
const open = ref(false)

function pick(id: string) {
  open.value = false
  if (id !== props.current) emit('pick', id)
}
const when = (ms: number) => fmtDateTime(new Date(ms).toISOString())
</script>

<template>
  <div class="mt-2 flex flex-wrap items-center gap-2" data-testid="ask-history">
    <button
      v-if="hasTurns" type="button" class="btn-secondary !px-2.5 !py-1 !text-xs" :disabled="busy"
      data-testid="ask-new-chat" @click="emit('fresh')"
    >
      {{ t('assist.chats.new') }}
    </button>
    <button
      v-if="chats.length" type="button" class="btn-secondary !px-2.5 !py-1 !text-xs" :aria-expanded="open"
      aria-controls="ask-chat-list" data-testid="ask-history-toggle" @click="open = !open"
    >
      {{ t('assist.chats.open', { n: chats.length }) }}
    </button>
    <ul
      v-if="open && chats.length" id="ask-chat-list"
      class="basis-full divide-y divide-stone-200 overflow-hidden rounded-md border border-stone-200 bg-white text-sm"
    >
      <li
        v-for="c in chats" :key="c.id" class="flex items-center gap-2 px-3 py-2"
        :class="{ 'bg-stone-100': c.id === current }"
      >
        <button
          type="button" class="min-w-0 flex-1 text-left disabled:cursor-not-allowed disabled:opacity-60"
          :disabled="busy" :aria-current="c.id === current ? 'true' : undefined" data-testid="ask-chat"
          @click="pick(c.id)"
        >
          <span class="block truncate font-medium text-stone-900">{{ c.title }}</span>
          <span class="block text-xs text-stone-500">
            {{ when(c.updated) }} · {{ t('assist.chats.turns', { n: c.turns.length }) }}
          </span>
        </button>
        <button
          type="button" class="shrink-0 rounded px-2 py-1 text-stone-500 hover:bg-stone-100 hover:text-stone-900
            disabled:opacity-60" :disabled="busy && c.id === current"
          :aria-label="t('assist.chats.remove', { title: c.title })" data-testid="ask-chat-remove"
          @click="emit('remove', c.id)"
        >
          ×
        </button>
      </li>
    </ul>
  </div>
</template>
