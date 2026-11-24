<script setup lang="ts">
import { computed, useId } from "vue";

import type { DrawnBox, FieldRow, Metrics } from "../api";
import { FONT_ADVANCE, FONT_FAMILY, MARKER_CHARS } from "../drawing";

const props = defineProps<{
  box: DrawnBox;
  x: number;
  y: number;
  metrics: Metrics;
  isNew: boolean;
  dragging: boolean;
  /** Briefly outlined after opening this diagram from a foreign box. */
  highlighted: boolean;
}>();

const fontSize = computed(() => props.metrics.charWidth / FONT_ADVANCE);
const inset = computed(() => props.metrics.padding / 2);
// Unique per box: sanitised keys could collide (a.b / a_b).
const clipId = `clip-${useId()}`;

function badges(row: FieldRow): string {
  // A primary key is unique anyway; "PK FK UK" would not fit the 6 reserved characters.
  return [row.pk && "PK", row.fk && "FK", row.uk && !row.pk && "UK"].filter(Boolean).join(" ");
}

function isField(row: unknown): row is FieldRow {
  return typeof row === "object" && row !== null && "type" in row;
}

// Baseline of a text line inside a band of ``height`` starting at ``top``.
function baseline(top: number, height: number): number {
  return top + height / 2 + fontSize.value * 0.35;
}
</script>

<template>
  <g
    :transform="`translate(${x} ${y})`"
    class="box"
    :class="{
      'box--new': isNew,
      'box--dragging': dragging,
      'box--enum': box.kind === 'enum',
      'box--foreign': box.foreign,
      'box--highlighted': highlighted,
    }"
    :data-key="box.key"
    :font-family="FONT_FAMILY"
    :font-size="fontSize"
  >
    <clipPath :id="clipId">
      <rect :width="box.width" :height="box.height" rx="6" />
    </clipPath>
    <rect class="box__body" :width="box.width" :height="box.height" rx="6" />
    <g :clip-path="`url(#${clipId})`">
      <rect class="box__header" :width="box.width" :height="metrics.header" />
      <text class="box__title" :x="inset" :y="baseline(0, metrics.header)" font-weight="700">
        {{ box.title }}
      </text>
      <template v-for="(row, i) in box.rows" :key="row.name + i">
        <line
          v-if="i > 0"
          class="box__divider"
          :x1="0"
          :x2="box.width"
          :y1="metrics.header + i * metrics.row"
          :y2="metrics.header + i * metrics.row"
        />
        <template v-if="isField(row)">
          <text class="box__badge" :x="inset" :y="baseline(metrics.header + i * metrics.row, metrics.row)">
            {{ badges(row) }}
          </text>
          <text
            class="box__name"
            :x="inset + MARKER_CHARS * metrics.charWidth"
            :y="baseline(metrics.header + i * metrics.row, metrics.row)"
          >
            {{ row.name }}
          </text>
          <text
            class="box__type"
            :x="box.width - inset"
            :y="baseline(metrics.header + i * metrics.row, metrics.row)"
            text-anchor="end"
          >
            {{ row.type }}{{ row.nullable ? "?" : "" }}
          </text>
        </template>
        <text v-else class="box__name" :x="inset" :y="baseline(metrics.header + i * metrics.row, metrics.row)">
          {{ row.name }}
        </text>
      </template>
    </g>
    <rect class="box__frame" :width="box.width" :height="box.height" rx="6" />
    <g v-if="isNew" :transform="`translate(${box.width - 44} ${-10})`">
      <rect class="box__chip" width="40" height="18" rx="9" />
      <text class="box__chip-text" x="20" y="13" text-anchor="middle" font-size="10" font-weight="700">NEW</text>
    </g>
  </g>
</template>

<style scoped>
.box {
  cursor: grab;
}
.box--dragging {
  cursor: grabbing;
}
.box__body {
  fill: var(--erd-box-bg);
}
.box__header {
  fill: var(--erd-header);
}
.box--enum .box__header {
  fill: var(--erd-enum-header);
}
.box__frame {
  fill: none;
  stroke: var(--erd-border-strong);
  stroke-width: 1;
}
.box--new .box__frame {
  stroke: var(--erd-primary);
  stroke-width: 2;
}
.box--dragging .box__frame {
  stroke: var(--erd-primary);
}
.box--foreign {
  cursor: pointer;
}
.box--foreign .box__body,
.box--foreign .box__header {
  fill: var(--erd-bg-muted);
}
.box--foreign .box__frame {
  stroke-dasharray: 4 3;
}
.box--foreign .box__title {
  fill: var(--erd-text-muted);
}
.box--highlighted .box__frame {
  stroke: var(--erd-primary);
  stroke-width: 3;
}
.box__divider {
  stroke: var(--erd-border);
}
.box__title {
  fill: var(--erd-header-text);
}
/* Not for foreign boxes: an enum shown as a foreign box keeps the muted title
   (`.box--foreign .box__title` above). */
.box--enum:not(.box--foreign) .box__title {
  fill: var(--erd-enum-title);
}
.box__name {
  fill: var(--erd-text);
}
.box__type {
  fill: var(--erd-text-muted);
}
.box__badge {
  fill: var(--erd-primary);
  font-weight: 700;
}
.box__chip {
  fill: var(--erd-primary);
}
.box__chip-text {
  fill: var(--erd-accent-text);
}
text {
  user-select: none;
}
</style>
