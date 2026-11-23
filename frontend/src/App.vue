<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import { fetchDiagrams, saveLayout, type AllPositions, type DiagramJson, type Diagrams, type Position, type View } from "./api";
import DiagramCanvas from "./components/DiagramCanvas.vue";
import DiagramList from "./components/DiagramList.vue";
import StudioToolbar from "./components/StudioToolbar.vue";

const OVERVIEW = "_overview";
const EMPTY: ReadonlySet<string> = new Set();

const toast = useToast();

const loaded = ref<Diagrams | null>(null);
const loadError = ref<string | null>(null);
// Per diagram: every box's position, and the boxes placed automatically (NEW until saved).
const positions = ref<AllPositions>({});
const newKeys = ref<Record<string, Set<string>>>({});
const revision = ref<string | null>(null);
const current = ref(OVERVIEW);
// Pan and zoom per diagram, so switching back shows it as it was left.
const views: Record<string, View> = {};
// What the file lacks before anything is dragged (from the server); cleared by a save.
const pendingShown = ref(false);
const moved = ref<Set<string>>(new Set());
// Drags per diagram, so a save only clears the diagrams nothing moved in while it ran.
const edits: Record<string, number> = {};
const saving = ref(false);

const dirty = computed(() => pendingShown.value || moved.value.size > 0);

const diagram = computed<DiagramJson | null>(
  () => loaded.value?.diagrams.find((d) => d.name === current.value) ?? null,
);

const banner = computed(() => {
  const data = loaded.value;
  if (!data || !pendingShown.value) return null;
  const { placed, diagrams, dropped, created } = data.pending;
  if (placed) {
    return `${placed} new ${placed === 1 ? "box was" : "boxes were"} placed automatically in ${diagrams} ${diagrams === 1 ? "diagram" : "diagrams"} — save to keep them.`;
  }
  if (created) return `No layout file yet — save to create ${data.layoutPath}.`;
  if (dropped) {
    return `The layout file has ${dropped} stale ${dropped === 1 ? "entry" : "entries"} — save to drop them.`;
  }
  return null;
});

// Diagrams with moved boxes, or with boxes placed automatically and not saved yet.
const unsaved = computed(() => {
  const names = new Set(moved.value);
  for (const [name, keys] of Object.entries(newKeys.value)) if (keys.size) names.add(name);
  return names;
});

// The current diagram is kept in the URL hash, so a reload stays on it.
function hashDiagram(): string | null {
  const match = /^#diagram=(.*)$/.exec(window.location.hash);
  if (!match) return null;
  try {
    return decodeURIComponent(match[1]);
  } catch {
    return null;
  }
}

function select(name: string): void {
  if (name !== current.value) focusKey.value = undefined;
  current.value = name;
  history.replaceState(null, "", `#diagram=${encodeURIComponent(name)}`);
}

// The diagram the hash names, or the overview for a missing or unknown one.
function hashTarget(): string {
  const wanted = hashDiagram();
  return loaded.value?.diagrams.some((d) => d.name === wanted) ? wanted! : OVERVIEW;
}

// Editing the hash in the address bar (or a link to it) switches diagrams.
function onHashChange(): void {
  if (loaded.value) select(hashTarget());
}

// Set when a diagram is opened from a foreign box: that entity is centred there.
const focusKey = ref<string | undefined>(undefined);

function onOpen(key: string): void {
  const group = loaded.value?.boxes[key]?.group;
  if (!group || !loaded.value?.diagrams.some((d) => d.name === group)) return;
  select(group);
  focusKey.value = key; // after select(), which clears it
}

function onView(view: View): void {
  views[current.value] = view;
}

function onMove(key: string, position: Position): void {
  const name = current.value;
  positions.value = { ...positions.value, [name]: { ...positions.value[name], [key]: position } };
  moved.value = new Set([...moved.value, name]);
  edits[name] = (edits[name] ?? 0) + 1;
}

async function save(): Promise<void> {
  if (!loaded.value || saving.value || !dirty.value) return;
  saving.value = true;
  const editsAtSave = { ...edits };
  try {
    const outcome = await saveLayout(revision.value, positions.value);
    if (outcome.ok) {
      revision.value = outcome.revision;
      moved.value = new Set([...moved.value].filter((name) => edits[name] !== editsAtSave[name]));
      pendingShown.value = false;
      newKeys.value = {};
      toast.remove(SAVE_ERROR);
      toast.add({ title: `Saved to ${outcome.saved}`, color: "success", icon: "i-lucide-check" });
    } else if (outcome.conflict) {
      showError(
        "The layout file or the models changed since this page loaded (on disk or from another tab). Reload to get them — saving now would overwrite them.",
      );
    } else {
      showError(`Could not save: ${outcome.message}`);
    }
  } finally {
    saving.value = false;
  }
}

// One sticky error toast at a time: adding it again with the same id updates the open
// one instead of stacking (removing it first would let its exit animation drop the new one).
const SAVE_ERROR = "save-error";

function showError(title: string): void {
  toast.add({ id: SAVE_ERROR, title, color: "error", icon: "i-lucide-circle-alert", duration: 0 });
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
  window.addEventListener("hashchange", onHashChange);
  try {
    const data = await fetchDiagrams();
    positions.value = Object.fromEntries(data.diagrams.map((d) => [d.name, { ...d.positions }]));
    newKeys.value = Object.fromEntries(data.diagrams.map((d) => [d.name, new Set(d.new)]));
    revision.value = data.revision;
    const { placed, dropped, created } = data.pending;
    pendingShown.value = created || placed > 0 || dropped > 0;
    loaded.value = data;
    // An unknown name in the hash is replaced, so the URL names what is shown.
    if (window.location.hash) select(hashTarget());
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
  window.removeEventListener("beforeunload", onBeforeUnload);
  window.removeEventListener("hashchange", onHashChange);
});
</script>

<template>
  <UApp>
    <div class="flex h-screen flex-col">
      <StudioToolbar :title="diagram?.label ?? 'Overview'" :dirty="dirty" :saving="saving" @save="save" />
      <UAlert v-if="banner" :title="banner" color="primary" variant="subtle" icon="i-lucide-sparkles" class="rounded-none" />
      <div class="flex min-h-0 flex-1">
        <DiagramList
          v-if="loaded && loaded.diagrams.length > 1"
          :diagrams="loaded.diagrams"
          :boxes="loaded.boxes"
          :current="current"
          :unsaved="unsaved"
          @select="select"
        />
        <main class="min-h-0 min-w-0 flex-1">
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
            v-else-if="loaded && diagram"
            :key="current"
            :boxes="loaded.boxes"
            :diagram="diagram"
            :metrics="loaded.metrics"
            :positions="positions[current]"
            :new-keys="newKeys[current] ?? EMPTY"
            :project-path="loaded.projectPath"
            :initial-view="views[current]"
            :focus-key="focusKey"
            @move="onMove"
            @open="onOpen"
            @view="onView"
          />
        </main>
      </div>
    </div>
  </UApp>
</template>
