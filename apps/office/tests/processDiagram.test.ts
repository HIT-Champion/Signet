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

// Sơ đồ quy trình của văn bản (#603): dữ liệu Action documentProcess (hợp đồng K5) thành hình SVG đúng loại phần tử
// BPMN, nhãn vừa hình, đường đủ điểm, danh sách bước dạng chữ đúng thứ tự và trạng thái; trang văn bản mở sơ đồ
// trong <details> ở cột chính, gọi đúng Action, không đụng hai tab Dòng thời gian / Lịch sử; đủ chữ hai thứ tiếng.

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'

const { diagramView, wrap } = await import('../app/utils/processDiagram.ts')
const source = (rel: string) => readFileSync(new URL(rel, import.meta.url), 'utf8')

const node = (id: string, kind: string, x: number, y: number, w: number, h: number, state = '',
  name: string | null = id) => ({ id, kind, name, x, y, w, h, state })
// một đoạn của van-ban-den: vào sổ → chỉ đạo (timer hạn trên mép) → gateway → phân công / xử lý → kết thúc
const SAMPLE = {
  key: 'van-ban-den', width: 900, height: 300,
  nodes: [
    node('batDau', 'startEvent', 20, 62, 36, 36, 'done', 'Vào sổ'),
    node('chiDao', 'userTask', 100, 40, 130, 80, 'done', 'Lãnh đạo chỉ đạo'),
    node('hanChiDao', 'boundaryEvent', 182, 102, 36, 36, 'done', 'Quá hạn'),
    node('sauChiDao', 'exclusiveGateway', 280, 55, 50, 50, 'done', null),
    node('phanCong', 'userTask', 380, 0, 130, 80, 'active', 'Phân công chuyên viên'),
    node('xuLy', 'userTask', 380, 140, 130, 80, '', 'Chuyên viên xử lý'),
    node('tach', 'parallelGateway', 560, 55, 50, 50),
    node('ghiSo', 'serviceTask', 650, 40, 130, 80),
    node('daXuLy', 'endEvent', 820, 62, 36, 36),
  ],
  edges: [
    { id: 'f1', name: null, points: [56, 80, 100, 80], state: 'done' },
    { id: 'f3', name: 'Cần phân công', points: [305, 55, 305, 40, 380, 40], state: 'done' },
    { id: 'f4', name: '', points: [305, 105, 305, 180, 380, 180], state: '' },
    { id: 'hong', name: null, points: [1, 2, 3], state: 'done' },
  ],
}

test('mỗi loại phần tử BPMN thành đúng hình', () => {
  const view = diagramView(SAMPLE)
  assert.equal(view.viewBox, '0 0 900 300')
  const by = new Map(view.shapes.map((s) => [s.id, s]))
  assert.deepEqual(by.get('batDau'), {
    id: 'batDau', kind: 'startEvent', name: 'Vào sổ', state: 'done', shape: 'circle', cx: 38, cy: 80, r: 18,
    ring: 'thin', label: { x: 38, y: 114, anchor: 'middle', lines: ['Vào sổ'] },
  })
  assert.equal(by.get('daXuLy')!.shape === 'circle' && by.get('daXuLy')!.ring, 'thick')
  assert.equal(by.get('hanChiDao')!.shape === 'circle' && by.get('hanChiDao')!.ring, 'double')
  assert.deepEqual(by.get('hanChiDao')!.label.lines, [], 'boundary trên mép task: không nhãn, tên ở <title>')
  const gw = by.get('sauChiDao')!
  assert.ok(gw.shape === 'diamond')
  assert.equal(gw.points, '305,55 330,80 305,105 280,80')
  assert.equal(gw.mark, 'M 295 70 L 315 90 M 315 70 L 295 90')
  assert.equal(gw.name, 'sauChiDao', 'gateway không tên: tên là id để <title> không trống')
  assert.deepEqual(gw.label.lines, [], 'gateway không tên: không có nhãn trên sơ đồ')
  const par = by.get('tach')!
  assert.ok(par.shape === 'diamond' && par.mark === 'M 585 66 L 585 94 M 571 80 L 599 80')
  const task = by.get('phanCong')!
  assert.ok(task.shape === 'rect')
  assert.deepEqual([task.x, task.y, task.w, task.h, task.state], [380, 0, 130, 80, 'active'])
  assert.equal(task.label.x, 445, 'nhãn task giữa hình')
  assert.ok(task.label.lines.length >= 2 && task.label.lines.join(' ') === 'Phân công chuyên viên')
})

test('đường thành path đủ điểm, nhãn nhánh ở đoạn dài nhất; đường hỏng bị bỏ', () => {
  const view = diagramView(SAMPLE)
  assert.deepEqual(view.edges.map((e) => e.id), ['f1', 'f3', 'f4'])
  assert.equal(view.edges[0]!.d, 'M 56 80 L 100 80')
  assert.equal(view.edges[1]!.d, 'M 305 55 L 305 40 L 380 40')
  // đoạn ngang dài nhất (305 → 380): chữ ở dưới đường, xuống dòng cho vừa khoảng giữa hai hình
  assert.deepEqual(view.edges[1]!.label, { x: 342.5, y: 55, anchor: 'middle', lines: ['Cần phân', 'công'] })
  assert.equal(view.edges[0]!.label, null)
  assert.equal(view.edges[2]!.label, null, 'tên rỗng: không nhãn')
  assert.deepEqual(view.edges.map((e) => e.state), ['done', 'done', ''])
})

test('danh sách bước: đã qua, đang chờ, task chưa tới; theo x rồi y; bỏ gateway, start, service chưa tới', () => {
  assert.deepEqual(diagramView(SAMPLE).steps, [
    { id: 'chiDao', name: 'Lãnh đạo chỉ đạo', state: 'done' },
    { id: 'hanChiDao', name: 'Quá hạn', state: 'done' },
    { id: 'phanCong', name: 'Phân công chuyên viên', state: 'active' },
    { id: 'xuLy', name: 'Chuyên viên xử lý', state: '' },
  ])
})

test('nhãn đường dọc bên phải; gateway có tên thì nhãn trên hình; nhãn lố mép dưới thì nới khung', () => {
  const view = diagramView({
    key: 'x', width: 300, height: 100,
    nodes: [node('g', 'exclusiveGateway', 100, 40, 50, 50, '', 'Đồng ý?'), node('e', 'endEvent', 200, 60, 36, 36)],
    edges: [{ id: 'v', name: 'Trả lại', points: [125, 90, 125, 200], state: '' }],
  })
  assert.deepEqual(view.edges[0]!.label, { x: 131, y: 149, anchor: 'start', lines: ['Trả lại'] })
  assert.deepEqual(view.shapes[0]!.label, { x: 125, y: 34, anchor: 'middle', lines: ['Đồng ý?'] })
  assert.equal(view.height, 117, 'nhãn của e ở y 112 + 5')
  // có đường chạm đỉnh trên: chỗ đó của đường, gateway không có nhãn (tên vẫn ở <title>)
  const top = diagramView({
    key: 'x', width: 300, height: 100, nodes: [node('g', 'exclusiveGateway', 100, 40, 50, 50, '', 'Đồng ý?')],
    edges: [{ id: 'up', name: null, points: [125.5, 40, 125.5, 0, 200, 0], state: '' }],
  })
  assert.deepEqual(top.shapes[0]!.label.lines, [])
  assert.equal(top.shapes[0]!.name, 'Đồng ý?')
})

test('trạng thái lạ là chưa tới; node thiếu tọa độ bị bỏ; thiếu width, height thì tính từ node', () => {
  const view = diagramView({
    key: 'x', width: 0, height: Number.NaN,
    nodes: [node('a', 'userTask', 10, 10, 100, 60, 'running'), node('b', 'userTask', Number.NaN, 0, 10, 10),
      node('c', 'userTask', 0, 0, 0, 10)],
    edges: [],
  })
  assert.deepEqual(view.shapes.map((s) => [s.id, s.state]), [['a', '']])
  assert.equal(view.viewBox, '0 0 130 90')
})

test('cắt tên theo từ, tối đa số dòng, dòng cuối thừa thì có dấu …', () => {
  assert.deepEqual(wrap('Lãnh đạo chỉ đạo', 200), ['Lãnh đạo chỉ đạo'])
  assert.deepEqual(wrap('Lãnh đạo chỉ đạo', 60), ['Lãnh đạo', 'chỉ đạo'])
  const cut = wrap('một hai ba bốn năm sáu bảy tám chín mười', 40, 2)
  assert.equal(cut.length, 2)
  assert.ok(cut[1]!.endsWith('…'))
  assert.deepEqual(wrap('  ', 100), [])
})

test('trang văn bản: <details> trong cột chính gọi Action documentProcess, hai tab giữ nguyên', () => {
  const page = source('../app/pages/van-ban/[id].vue')
  const main = page.slice(page.indexOf('<div class="sg-doc-main">'), page.indexOf('<aside class="sg-doc-side">'))
  assert.match(main, /<details[^>]*data-testid="process"[^>]*:data-state="processState"/)
  assert.match(main, /<ProcessDiagram\b/)
  // đúng hợp đồng K5 (db/metadata/actions.graphql của PR A)
  const fields = /documentProcess\(documentId: \$id\) \{\s*key width height\s*nodes \{ id kind name x y w h state \}\s*/
  assert.match(page, new RegExp(fields.source + /edges \{ id name points state \}/.source))
  assert.match(page, /e\.code === 'no_process'/)
  assert.match(page, /if \(processOpen\.value\) void loadProcess\(\)/, 'load() nạp lại sơ đồ khi mục đang mở')
  assert.equal((page.match(/role="tab"/g) ?? []).length, 2, 'không thêm tab thứ ba')
  const diagram = source('../app/components/ProcessDiagram.vue')
  assert.match(diagram, /from '~\/utils\/processDiagram'/)
  assert.match(diagram, /role="img"/)
  assert.match(diagram, /<title>/)
  assert.doesNotMatch(diagram + page, /bpmn-js/)
})

test('chữ doc.process.* có đủ ở vi và en', () => {
  const vi = JSON.parse(source('../app/locales/vi.json')).doc.process
  const en = JSON.parse(source('../app/locales/en.json')).doc.process
  const keys = ['title', 'label', 'loading', 'none', 'done', 'active', 'todo', 'steps']
  for (const k of keys) assert.ok(vi?.[k] && en?.[k], `doc.process.${k}`)
  assert.deepEqual(Object.keys(vi).sort(), Object.keys(en).sort())
})
