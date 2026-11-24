<script setup lang="ts">
import { computed } from "vue";

import type { EdgeEnd } from "../api";
import { angle, edgeLine, endMarker, selfLoop, type Rect } from "../geometry";

const props = defineProps<{
  from: Rect;
  to: Rect;
  fromKey: string;
  toKey: string;
  /** Sideways offset, or for a self-reference the loop's index. */
  offset: number;
  fromEnd?: EdgeEnd;
  toEnd?: EdgeEnd;
  label?: string;
  dashed?: boolean;
}>();

const shape = computed(() => {
  if (props.fromKey === props.toKey) {
    const loop = selfLoop(props.from, props.offset);
    return { path: loop.path, start: loop.start, end: loop.end, startAngle: loop.startAngle, endAngle: loop.endAngle };
  }
  const { start, end } = edgeLine(props.from, props.to, props.offset, props.fromKey, props.toKey);
  return {
    path: `M ${start.x} ${start.y} L ${end.x} ${end.y}`,
    start,
    end,
    startAngle: angle(start, end),
    endAngle: angle(end, start),
  };
});

const markers = computed(() => {
  const found = [];
  if (props.fromEnd) found.push(endMarker(shape.value.start, shape.value.startAngle, props.fromEnd));
  if (props.toEnd) found.push(endMarker(shape.value.end, shape.value.endAngle, props.toEnd));
  return found;
});
</script>

<template>
  <g class="edge" :class="{ 'edge--dashed': dashed }">
    <title v-if="label">{{ label }}</title>
    <!-- A wide transparent stroke makes the tooltip easy to hit. -->
    <path class="edge__hit" :d="shape.path" />
    <path class="edge__line" :d="shape.path" />
    <template v-for="(marker, i) in markers" :key="i">
      <path class="edge__line" :d="marker.lines" />
      <path v-if="marker.circle" class="edge__circle" :d="marker.circle" />
    </template>
  </g>
</template>

<style scoped>
.edge__line {
  fill: none;
  stroke: var(--erd-text-muted);
  stroke-width: 1.25;
}
.edge--dashed .edge__line {
  stroke-dasharray: 4 4;
}
.edge__hit {
  fill: none;
  stroke: transparent;
  stroke-width: 10;
}
.edge__circle {
  fill: var(--erd-bg-muted);
  stroke: var(--erd-text-muted);
  stroke-width: 1.25;
}
</style>
