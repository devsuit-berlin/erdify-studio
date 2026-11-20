<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { fetchOverview, saveLayout, type Overview, type Position } from "./api";
import DiagramCanvas from "./components/DiagramCanvas.vue";
import StudioToolbar from "./components/StudioToolbar.vue";

const toast = useToast();

const overview = ref<Overview | null>(null);
const loadError = ref<string | null>(null);
const positions = ref<Record<string, Position>>({});
const revision = ref<string | null>(null);
const newKeys = ref<Set<string>>(new Set());
// What the file lacks before anything is dragged (from the server); cleared by a save.
const pendingShown = ref(false);
const moved = ref(false);
// Counts drags, so a save only clears "unsaved" when nothing moved while it ran.
let edits = 0;
const saving = ref(false);

const dirty = computed(() => pendingShown.value || moved.value);

const banner = computed(() => {
  const loaded = overview.value;
  if (!loaded || !pendingShown.value) return null;
  const { placed, groupChanges, created } = loaded.pending;
  if (created) return `No layout file yet — save to create ${loaded.layoutPath}.`;
  if (placed) {
    return `${placed} new ${placed === 1 ? "box was" : "boxes were"} placed automatically — save to keep them.`;
  }
  if (groupChanges) {
    return `The layout file is out of date in ${groupChanges} group-diagram ${groupChanges === 1 ? "entry" : "entries"} — save to update it.`;
  }
  return null;
});

function onMove(key: string, position: Position): void {
  positions.value = { ...positions.value, [key]: position };
  moved.value = true;
  edits += 1;
}

async function save(): Promise<void> {
  if (!overview.value || saving.value || !dirty.value) return;
  saving.value = true;
  const editsAtSave = edits;
  try {
    const outcome = await saveLayout(revision.value, positions.value);
    if (outcome.ok) {
      revision.value = outcome.revision;
      moved.value = edits !== editsAtSave;
      pendingShown.value = false;
      newKeys.value = new Set();
      toast.add({ title: `Saved to ${outcome.saved}`, color: "success", icon: "i-lucide-check" });
    } else if (outcome.conflict) {
      toast.add({
        title: "The layout file changed since this page loaded (on disk or from another tab). Reload to get it — saving now would overwrite it.",
        color: "error",
        icon: "i-lucide-circle-alert",
        duration: 0,
      });
    } else {
      toast.add({ title: `Could not save: ${outcome.message}`, color: "error", icon: "i-lucide-circle-alert", duration: 0 });
    }
  } finally {
    saving.value = false;
  }
}

function onKey(event: KeyboardEvent): void {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "s") {
    event.preventDefault();
    void save();
  }
}

function onBeforeUnload(event: BeforeUnloadEvent): void {
  if (dirty.value) {
    event.preventDefault();
    event.returnValue = "";
  }
}

onMounted(async () => {
  window.addEventListener("keydown", onKey);
  window.addEventListener("beforeunload", onBeforeUnload);
  try {
    const loaded = await fetchOverview();
    positions.value = Object.fromEntries(loaded.boxes.map((b) => [b.key, [b.x, b.y] as Position]));
    newKeys.value = new Set(loaded.boxes.filter((b) => b.new).map((b) => b.key));
    revision.value = loaded.revision;
    const { placed, groupChanges, created } = loaded.pending;
    pendingShown.value = created || placed > 0 || groupChanges > 0;
    overview.value = loaded;
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
  window.removeEventListener("beforeunload", onBeforeUnload);
});
</script>

<template>
  <UApp>
    <div class="flex h-screen flex-col">
      <StudioToolbar :dirty="dirty" :saving="saving" @save="save" />
      <UAlert v-if="banner" :title="banner" color="primary" variant="subtle" icon="i-lucide-sparkles" class="rounded-none" />
      <main class="min-h-0 flex-1">
        <div v-if="loadError" class="flex h-full items-center justify-center p-8">
          <UAlert
            color="error"
            icon="i-lucide-circle-alert"
            title="Could not load the diagram"
            :description="loadError"
            class="max-w-xl"
          />
        </div>
        <DiagramCanvas
          v-else-if="overview"
          :overview="overview"
          :positions="positions"
          :new-keys="newKeys"
          @move="onMove"
        />
      </main>
    </div>
  </UApp>
</template>
