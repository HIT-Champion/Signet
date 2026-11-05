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

// Sơ đồ quy trình của một văn bản (#603): Action documentProcess của svc-workflow trả bố cục BPMN DI của quy trình
// (van-ban-den, van-ban-di) kèm trạng thái từng bước đọc từ lịch sử Flowable. Ở đây chỉ đổi dữ liệu đó thành hình để
// components/ProcessDiagram.vue vẽ SVG trong trang: không bpmn-js (giấy phép bpmn.io không phải OSI), không thư
// viện vẽ, không tải gì ngoài.

export type StepState = 'done' | 'active' | ''

export interface ProcessNode {
  id: string
  kind: string            // tên thẻ BPMN: startEvent, userTask, exclusiveGateway, boundaryEvent…
  name: string | null
  x: number
  y: number
  w: number
  h: number
  state: string
}
export interface ProcessEdge { id: string; name: string | null; points: number[]; state: string }
export interface DocumentProcess {
  key: string
  width: number
  height: number
  nodes: ProcessNode[]
  edges: ProcessEdge[]
}

// y là đường chân chữ của dòng đầu; các dòng sau cách LINE_H
export interface Label { x: number; y: number; anchor: 'middle' | 'start'; lines: string[] }
interface ShapeBase { id: string; kind: string; name: string; state: StepState; label: Label }
export type Shape =
  | ShapeBase & { shape: 'circle'; cx: number; cy: number; r: number; ring: 'thin' | 'thick' | 'double' }
  | ShapeBase & { shape: 'diamond'; cx: number; cy: number; points: string; mark: string }
  | ShapeBase & { shape: 'rect'; x: number; y: number; w: number; h: number }
export interface EdgeView { id: string; d: string; state: StepState; label: Label | null }
export interface Step { id: string; name: string; state: StepState }
export interface DiagramView {
  viewBox: string
  width: number
  height: number
  shapes: Shape[]
  edges: EdgeView[]
  steps: Step[]
}

// cỡ chữ trên sơ đồ (px của viewBox) và số ký tự trung bình một dòng chứa được: ước lượng, SVG không tự xuống dòng
export const FONT = 12
const CHAR_W = 6.4
export const LINE_H = 15
const NEAR_LABEL = 120          // bề rộng nhãn dưới event, trên gateway
const STEP_KINDS = new Set(['userTask', 'serviceTask', 'endEvent', 'boundaryEvent'])

const num = (v: unknown) => typeof v === 'number' && Number.isFinite(v)
const stateOf = (s: unknown): StepState => (s === 'done' || s === 'active' ? s : '')
const r1 = (v: number) => Math.round(v * 10) / 10

/** Cắt tên theo từ cho vừa bề rộng (px); từ dài hơn một dòng đứng riêng một dòng. Tối đa maxLines dòng, dòng cuối
 *  thừa thì cắt và thêm "…". */
export function wrap(text: string, width: number, maxLines = 3): string[] {
  const per = Math.max(4, Math.floor(width / CHAR_W))
  const lines: string[] = []
  for (const word of text.split(/\s+/).filter(Boolean)) {
    const last = lines.length ? lines[lines.length - 1]! : null
    if (last !== null && last.length + 1 + word.length <= per) lines[lines.length - 1] = `${last} ${word}`
    else lines.push(word)
  }
  if (lines.length <= maxLines) return lines
  const kept = lines.slice(0, maxLines)
  kept[maxLines - 1] = `${kept[maxLines - 1]!.slice(0, per - 1)}…`
  return kept
}

// nhãn giữa task, dưới event, trên gateway. Boundary (timer trên mép task) không có nhãn: nhãn sẽ đè chữ của task
// chủ, tên của nó ở <title> và danh sách bước. Gateway có đường chạm đỉnh trên cũng vậy: chỗ trên hình là của đường,
// câu hỏi của gateway đã rõ qua nhãn các nhánh
function labelFor(n: ProcessNode, name: string, topUsed: boolean): Label {
  const x = r1(n.x + n.w / 2)
  if (!n.kind.endsWith('Event') && !n.kind.endsWith('Gateway')) {
    const lines = wrap(name, n.w - 12, Math.max(1, Math.floor((n.h - 8) / LINE_H)))
    return { x, y: r1(n.y + n.h / 2 - ((lines.length - 1) * LINE_H) / 2 + FONT / 3), anchor: 'middle', lines }
  }
  if (n.kind.endsWith('Gateway')) {
    const lines = name && !topUsed ? wrap(name, NEAR_LABEL, 2) : []
    return { x, y: r1(n.y - 6 - (lines.length - 1) * LINE_H), anchor: 'middle', lines }
  }
  const lines = name && n.kind !== 'boundaryEvent' ? wrap(name, NEAR_LABEL, 2) : []
  return { x, y: r1(n.y + n.h + FONT + 4), anchor: 'middle', lines }
}

function shapeOf(n: ProcessNode, topUsed: boolean): Shape {
  const name = (n.name ?? '').trim()
  const base = { id: n.id, kind: n.kind, name: name || n.id, state: stateOf(n.state) }
  const cx = r1(n.x + n.w / 2)
  const cy = r1(n.y + n.h / 2)
  if (n.kind.endsWith('Event')) {
    const ring = n.kind === 'endEvent' ? 'thick' : n.kind === 'startEvent' ? 'thin' : 'double'
    return { ...base, shape: 'circle', cx, cy, r: r1(Math.min(n.w, n.h) / 2), ring, label: labelFor(n, name, false) }
  }
  if (n.kind.endsWith('Gateway')) {
    const points = [[cx, n.y], [n.x + n.w, cy], [cx, n.y + n.h], [n.x, cy]].map((p) => p.map(r1).join(',')).join(' ')
    // dấu trong hình thoi: X là rẽ một nhánh (exclusive), + là chạy song song (parallel)
    const k = Math.min(n.w, n.h) / 5
    const [a, b, c, e] = [r1(cx - k), r1(cx + k), r1(cy - k), r1(cy + k)]
    const [a2, b2, c2, e2] = [r1(cx - 1.4 * k), r1(cx + 1.4 * k), r1(cy - 1.4 * k), r1(cy + 1.4 * k)]
    const mark = n.kind === 'exclusiveGateway' ? `M ${a} ${c} L ${b} ${e} M ${b} ${c} L ${a} ${e}`
      : n.kind === 'parallelGateway' ? `M ${cx} ${c2} L ${cx} ${e2} M ${a2} ${cy} L ${b2} ${cy}` : ''
    return { ...base, shape: 'diamond', cx, cy, points, mark, label: labelFor(n, name, topUsed) }
  }
  return { ...base, shape: 'rect', x: n.x, y: n.y, w: n.w, h: n.h, label: labelFor(n, base.name, false) }
}

// tên của đường (nhánh "Trả lại", "Giao phòng chủ trì"…) đặt ở đoạn dài nhất: đoạn ngang thì chữ ở dưới (trên đường
// là chỗ nhãn gateway), xuống dòng cho vừa khoảng giữa hai hình; đoạn dọc thì chữ bên phải
function edgeLabel(p: number[], name: string): Label {
  const len = (i: number) => Math.hypot(p[i + 2]! - p[i]!, p[i + 3]! - p[i + 1]!)
  let best = 0
  for (let i = 2; i + 3 < p.length; i += 2) if (len(i) > len(best)) best = i
  const [x1, y1, x2, y2] = p.slice(best, best + 4) as [number, number, number, number]
  if (Math.abs(x2 - x1) >= Math.abs(y2 - y1)) {
    const lines = wrap(name, Math.max(72, Math.abs(x2 - x1) - 8), 3)
    return { x: r1((x1 + x2) / 2), y: r1(Math.max(y1, y2) + FONT + 3), anchor: 'middle', lines }
  }
  const lines = wrap(name, NEAR_LABEL, 3)
  return { x: r1(x1 + 6), y: r1((y1 + y2) / 2 - ((lines.length - 1) * LINE_H) / 2 + FONT / 3), anchor: 'start', lines }
}

function edgeOf(e: ProcessEdge): EdgeView {
  const p = e.points
  const d = Array.from({ length: p.length / 2 }, (_, i) => `${i ? 'L' : 'M'} ${p[2 * i]} ${p[2 * i + 1]}`).join(' ')
  const name = (e.name ?? '').trim()
  return { id: e.id, d, state: stateOf(e.state), label: name ? edgeLabel(p, name) : null }
}

/**
 * Dữ liệu Action documentProcess → hình để vẽ: event là hình tròn, gateway là hình thoi, task là hình chữ nhật bo góc,
 * đường là path "M x y L …"; steps là danh sách bước dạng chữ cho trình đọc màn hình: bước đã qua, đang chờ (task,
 * kết thúc, timer đã bắn) cùng các task chưa tới, theo x rồi y. Node, đường thiếu tọa độ thì bỏ qua.
 */
export function diagramView(d: DocumentProcess): DiagramView {
  const nodes = (d.nodes ?? []).filter((n) => [n.x, n.y, n.w, n.h].every(num) && n.w > 0 && n.h > 0)
  const edges = (d.edges ?? []).filter((e) => Array.isArray(e.points) && e.points.length >= 4
    && e.points.length % 2 === 0 && e.points.every(num))
  // đỉnh trên của gateway có đầu đường nào chạm vào không (lệch 1.5px vẫn tính)
  const ends = edges.flatMap((e) => [e.points.slice(0, 2), e.points.slice(-2)])
  const topUsed = (n: ProcessNode) => ends.some(([x, y]) => Math.abs(x! - n.x - n.w / 2) <= 1.5
    && Math.abs(y! - n.y) <= 1.5)
  const shapes = nodes.map((n) => shapeOf(n, n.kind.endsWith('Gateway') && topUsed(n)))
  const width = num(d.width) && d.width > 0 ? d.width : Math.max(0, ...nodes.map((n) => n.x + n.w)) + 20
  // nhãn dưới event ở hàng cuối có thể lố mép dưới của DI: nới khung cho đủ chữ
  const bottom = Math.max(0, ...shapes.map((s) => s.label.y + (s.label.lines.length - 1) * LINE_H + 5))
  const height = Math.max(num(d.height) && d.height > 0 ? d.height : Math.max(0, ...nodes.map((n) => n.y + n.h)) + 20,
    Math.ceil(bottom))
  const steps = nodes
    .map((n, i) => ({ n, s: shapes[i]! }))
    .filter(({ s }) => STEP_KINDS.has(s.kind) && (s.state !== '' || s.kind === 'userTask'))
    .sort((a, b) => (a.n.x - b.n.x) || (a.n.y - b.n.y))
    .map(({ s }) => ({ id: s.id, name: s.name, state: s.state }))
  return { viewBox: `0 0 ${width} ${height}`, width, height, shapes, edges: edges.map(edgeOf), steps }
}
