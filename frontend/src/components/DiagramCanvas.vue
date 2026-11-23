<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import type { BoxDef, DiagramJson, DrawnBox, Metrics, Position, View } from "../api";
import { FIT_MARGIN, MAX_ZOOM, MIN_ZOOM } from "../drawing";
import { fanOffsets, type Rect } from "../geometry";
import BoxNode from "./BoxNode.vue";
import EdgeLine from "./EdgeLine.vue";

const props = defineProps<{
  boxes: Record<string, BoxDef>;
  diagram: DiagramJson;
  metrics: Metrics;
  positions: Record<string, Position>;
  newKeys: ReadonlySet<string>;
  projectPath: string;
  /** The view this diagram was left at; fitted when absent. */
  initialView?: View;
}>();

const emit = defineEmits<{ move: [key: string, position: Position]; view: [view: View] }>();

const svg = ref<SVGSVGElement | null>(null);
const view = ref<View>(props.initialView ?? { x: 0, y: 0, scale: 1 });
watch(view, (value) => emit("view", value));

// What this diagram draws; Python decided it (own and foreign keys, sizes, edges).
const drawn = computed<DrawnBox[]>(() => [
  ...props.diagram.own.map((key) => ({ key, ...props.boxes[key], foreign: false })),
  ...props.diagram.foreign.map((key) => {
    const [width, height] = props.diagram.foreignSizes[key];
    return { key, kind: "entity" as const, title: props.boxes[key].title, width, height, rows: [], foreign: true };
  }),
]);

const rects = computed(() => {
  const found: Record<string, Rect> = {};
  for (const box of drawn.value) {
    const [x, y] = props.positions[box.key] ?? props.diagram.positions[box.key];
    found[box.key] = { x, y, width: box.width, height: box.height };
  }
  return found;
});

const edges = computed(() => {
  const offsets = fanOffsets(props.diagram.edges);
  return props.diagram.edges.map((edge, i) => ({ edge, offset: offsets[i] }));
});

const enumLinks = computed(() => props.diagram.enumLinks);

// --- view: fit, zoom, pan -----------------------------------------------------------

function fit(): void {
  const all = Object.values(rects.value);
  const element = svg.value;
  if (!all.length || !element) {
    view.value = { x: FIT_MARGIN, y: FIT_MARGIN, scale: 1 };
    return;
  }
  const minX = Math.min(...all.map((r) => r.x));
  const minY = Math.min(...all.map((r) => r.y));
  const maxX = Math.max(...all.map((r) => r.x + r.width));
  const maxY = Math.max(...all.map((r) => r.y + r.height));
  const { width, height } = element.getBoundingClientRect();
  const scale = clamp(
    Math.min(
      (width - 2 * FIT_MARGIN) / Math.max(maxX - minX, 1),
      (height - 2 * FIT_MARGIN) / Math.max(maxY - minY, 1),
      1,
    ),
  );
  view.value = {
    scale,
    x: (width - (maxX - minX) * scale) / 2 - minX * scale,
    y: (height - (maxY - minY) * scale) / 2 - minY * scale,
  };
}

function clamp(scale: number): number {
  return Math.min(Math.max(scale, MIN_ZOOM), MAX_ZOOM);
}

/** Zoom by ``factor`` keeping the screen point ``(sx, sy)`` in place. */
function zoom(factor: number, sx?: number, sy?: number): void {
  const element = svg.value;
  if (!element) return;
  const box = element.getBoundingClientRect();
  const px = sx ?? box.width / 2;
  const py = sy ?? box.height / 2;
  const { x, y, scale } = view.value;
  const next = clamp(scale * factor);
  view.value = {
    scale: next,
    x: px - ((px - x) / scale) * next,
    y: py - ((py - y) / scale) * next,
  };
}

function onWheel(event: WheelEvent): void {
  event.preventDefault();
  const box = svg.value!.getBoundingClientRect();
  zoom(Math.exp(-event.deltaY * 0.0015), event.clientX - box.left, event.clientY - box.top);
}

let pan: { pointer: number; x: number; y: number; vx: number; vy: number } | null = null;

function onBackgroundDown(event: PointerEvent): void {
  if (event.button !== 0) return;
  pan = { pointer: event.pointerId, x: event.clientX, y: event.clientY, vx: view.value.x, vy: view.value.y };
  (event.currentTarget as Element).setPointerCapture(event.pointerId);
}

function onBackgroundMove(event: PointerEvent): void {
  if (!pan || pan.pointer !== event.pointerId) return;
  view.value = { ...view.value, x: pan.vx + event.clientX - pan.x, y: pan.vy + event.clientY - pan.y };
}

function onBackgroundUp(event: PointerEvent): void {
  if (pan?.pointer === event.pointerId) pan = null;
}

// --- drag a box ---------------------------------------------------------------------

const dragging = ref<{ key: string; pointer: number; x: number; y: number; bx: number; by: number } | null>(null);

// The dragged box is drawn last, on top of the others.
const ordered = computed(() => {
  const key = dragging.value?.key;
  return key ? [...drawn.value.filter((b) => b.key !== key), ...drawn.value.filter((b) => b.key === key)] : drawn.value;
});

// The pointer is captured by the <svg>, not the box: the dragged box is re-inserted
// on top, and an element leaving the DOM loses its pointer capture.
function onBoxDown(event: PointerEvent, key: string): void {
  if (event.button !== 0) return;
  event.stopPropagation();
  const rect = rects.value[key];
  dragging.value = { key, pointer: event.pointerId, x: event.clientX, y: event.clientY, bx: rect.x, by: rect.y };
  svg.value?.setPointerCapture(event.pointerId);
}

function onBoxMove(event: PointerEvent): void {
  const drag = dragging.value;
  if (!drag || drag.pointer !== event.pointerId) return;
  if ((event.buttons & 1) === 0) {
    dragging.value = null; // the release was missed (e.g. outside the window)
    return;
  }
  const { scale } = view.value;
  const x = Math.round(drag.bx + (event.clientX - drag.x) / scale);
  const y = Math.round(drag.by + (event.clientY - drag.y) / scale);
  const current = props.positions[drag.key];
  if (!current || current[0] !== x || current[1] !== y) {
    emit("move", drag.key, [x, y]);
  }
}

function onBoxUp(event: PointerEvent): void {
  if (dragging.value?.pointer === event.pointerId) dragging.value = null;
}

onMounted(() => {
  if (!props.initialView) fit();
});

defineExpose({ fit });
</script>

<template>
  <div class="relative h-full w-full overflow-hidden bg-muted">
    <svg
      ref="svg"
      class="h-full w-full touch-none select-none"
      @wheel="onWheel"
      @pointermove="onBoxMove"
      @pointerup="onBoxUp"
      @pointercancel="onBoxUp"
      @lostpointercapture="onBoxUp"
    >
      <rect
        class="cursor-move"
        width="100%"
        height="100%"
        fill="transparent"
        @pointerdown="onBackgroundDown"
        @pointermove="onBackgroundMove"
        @pointerup="onBackgroundUp"
        @pointercancel="onBackgroundUp"
      />
      <g :transform="`translate(${view.x} ${view.y}) scale(${view.scale})`">
        <EdgeLine
          v-for="link in enumLinks"
          :key="`${link.enum}->${link.entity}`"
          :from="rects[link.enum]"
          :to="rects[link.entity]"
          :from-key="link.enum"
          :to-key="link.entity"
          :offset="0"
          dashed
        />
        <EdgeLine
          v-for="({ edge, offset }, i) in edges"
          :key="i"
          :from="rects[edge.from]"
          :to="rects[edge.to]"
          :from-key="edge.from"
          :to-key="edge.to"
          :offset="offset"
          :from-end="edge.fromEnd"
          :to-end="edge.toEnd"
          :label="edge.label"
        />
        <BoxNode
          v-for="box in ordered"
          :key="box.key"
          :box="box"
          :x="rects[box.key].x"
          :y="rects[box.key].y"
          :metrics="metrics"
          :is-new="newKeys.has(box.key)"
          :dragging="dragging?.key === box.key"
          @pointerdown="onBoxDown($event, box.key)"
        />
      </g>
    </svg>
    <p
      v-if="!drawn.length"
      class="pointer-events-none absolute inset-0 flex items-center justify-center text-muted"
    >
      No entities found in {{ projectPath }}.
    </p>
    <div class="absolute right-4 bottom-4 flex gap-1">
      <UButton icon="i-lucide-minus" color="neutral" variant="outline" aria-label="Zoom out" @click="zoom(1 / 1.25)" />
      <UButton icon="i-lucide-plus" color="neutral" variant="outline" aria-label="Zoom in" @click="zoom(1.25)" />
      <UButton icon="i-lucide-maximize" color="neutral" variant="outline" aria-label="Fit to view" @click="fit" />
    </div>
  </div>
</template>
