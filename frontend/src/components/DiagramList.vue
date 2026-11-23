<script setup lang="ts">
import type { DiagramJson } from "../api";

defineProps<{
  diagrams: DiagramJson[];
  current: string;
  unsaved: ReadonlySet<string>;
}>();
defineEmits<{ select: [name: string] }>();

const OVERVIEW = "_overview";

// Own entities only: enums are drawn but not counted.
function entityCount(diagram: DiagramJson): number {
  return diagram.own.filter((key) => !key.startsWith("enum:")).length;
}
</script>

<template>
  <nav class="flex w-56 shrink-0 flex-col gap-0.5 overflow-y-auto border-r border-default p-2" aria-label="Diagrams">
    <button
      v-for="diagram in diagrams"
      :key="diagram.name"
      type="button"
      class="flex items-center gap-2 rounded-md px-2 py-1.5 text-left text-sm hover:bg-elevated"
      :class="diagram.name === current ? 'bg-elevated font-semibold text-highlighted' : 'text-default'"
      :aria-current="diagram.name === current ? 'page' : undefined"
      @click="$emit('select', diagram.name)"
    >
      <span class="min-w-0 flex-1 truncate" :title="diagram.label">{{ diagram.label }}</span>
      <span v-if="diagram.name !== OVERVIEW" class="text-xs text-muted">{{ entityCount(diagram) }}</span>
      <span
        v-if="unsaved.has(diagram.name)"
        class="size-2 shrink-0 rounded-full bg-warning"
        title="Unsaved changes"
        aria-label="Unsaved changes"
      />
    </button>
  </nav>
</template>
