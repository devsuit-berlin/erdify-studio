<script setup lang="ts">
import { onMounted, ref } from "vue";

import { fetchOverview, type Overview, type Position } from "./api";
import DiagramCanvas from "./components/DiagramCanvas.vue";

const overview = ref<Overview | null>(null);
const loadError = ref<string | null>(null);
const positions = ref<Record<string, Position>>({});
const newKeys = ref<Set<string>>(new Set());

onMounted(async () => {
  try {
    const loaded = await fetchOverview();
    positions.value = Object.fromEntries(loaded.boxes.map((b) => [b.key, [b.x, b.y] as Position]));
    newKeys.value = new Set(loaded.boxes.filter((b) => b.new).map((b) => b.key));
    overview.value = loaded;
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  }
});
</script>

<template>
  <UApp>
    <div class="flex h-screen flex-col">
      <header class="flex items-center gap-3 border-b border-default px-4 py-2">
        <span class="font-semibold">erdify-studio · Overview</span>
      </header>
      <main class="min-h-0 flex-1">
        <div v-if="loadError" class="flex h-full items-center justify-center p-8">
          <UAlert color="error" icon="i-lucide-circle-alert" title="Could not load the diagram" :description="loadError" class="max-w-xl" />
        </div>
        <DiagramCanvas v-else-if="overview" :overview="overview" :positions="positions" :new-keys="newKeys" />
      </main>
    </div>
  </UApp>
</template>
