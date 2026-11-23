<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";

import {
  downloadSvg,
  fetchDiagrams,
  fetchStatus,
  mergeDiagrams,
  saveLayout,
  Unreachable,
  type AllPositions,
  type DiagramJson,
  type Diagrams,
  type Position,
  type View,
} from "./api";
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

// Live reload: the server re-parses the models; the page polls what changed.
const POLL_MS = 1000;
// The model fingerprint the page shows (from GET /api/status).
const model = ref<string | null>(null);
// Why the server shows the last good state (a model file that can't be loaded).
const loadIssue = ref<string | null>(null);
// The layout file on disk differs from the one this page read or wrote.
const layoutChanged = ref(false);
const serverGone = ref(false);
const draggingBox = ref(false);
let polling = false;
let failedPolls = 0;
// Bumped by every drag and every save: a merge that started before one of them would
// overwrite it, so its response is dropped (the next poll merges again).
let localVersion = 0;
// Why the last merge of changed models failed (shown until a merge works again).
const mergeIssue = ref<string | null>(null);
let pollTimer: number | undefined;

// Only outdated SVGs: Save fixes them, but nothing was edited — no "Unsaved changes"
// badge, no prompt on leaving.
const pendingLayout = computed(() => {
  const pending = loaded.value?.pending;
  return !!pending && pendingShown.value && (pending.created || pending.placed > 0 || pending.dropped > 0);
});
const svgsOnly = computed(() => (loaded.value?.pending.svgs ?? 0) > 0 && !pendingLayout.value);
const dirty = computed(() => pendingLayout.value || moved.value.size > 0);
const saveable = computed(() => dirty.value || (pendingShown.value && svgsOnly.value));

const diagram = computed<DiagramJson | null>(
  () => loaded.value?.diagrams.find((d) => d.name === current.value) ?? null,
);

const banner = computed(() => {
  const data = loaded.value;
  if (!data || !pendingShown.value) return null;
  const { placed, diagrams, dropped, created, svgs } = data.pending;
  if (placed) {
    return `${placed} new ${placed === 1 ? "box was" : "boxes were"} placed automatically in ${diagrams} ${diagrams === 1 ? "diagram" : "diagrams"} — save to keep them.`;
  }
  if (created) return `No layout file yet — save to create ${data.layoutPath}.`;
  if (dropped) {
    return `The layout file has ${dropped} stale ${dropped === 1 ? "entry" : "entries"} — save to drop them.`;
  }
  if (svgs && data.exportPath) return `The SVGs in ${data.exportPath} are out of date — save to update them.`;
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

// Editing the hash in the address bar (or a link to it) switches diagrams; an unknown
// `#diagram=` value goes to the overview, any other hash (`#foo`, `#`) is left alone.
function onHashChange(): void {
  if (loaded.value && hashDiagram() !== null) select(hashTarget());
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

// Show a payload: positions, NEW marks (kept for boxes that are still there) and what
// Save would change. Used on load and after every model change.
function apply(data: Diagrams, { initial }: { initial: boolean }): void {
  const before = newKeys.value;
  positions.value = Object.fromEntries(data.diagrams.map((d) => [d.name, { ...d.positions }]));
  newKeys.value = Object.fromEntries(
    data.diagrams.map((d) => {
      const kept = initial ? [] : [...(before[d.name] ?? [])].filter((key) => key in d.positions);
      return [d.name, new Set([...d.new, ...kept])];
    }),
  );
  if (initial) revision.value = data.revision;
  const { placed, dropped, created, svgs } = data.pending;
  pendingShown.value = created || placed > 0 || dropped > 0 || svgs > 0;
  moved.value = new Set([...moved.value].filter((name) => data.diagrams.some((d) => d.name === name)));
  loaded.value = data;
  if (!data.diagrams.some((d) => d.name === current.value)) select(OVERVIEW);
}

// The models changed: merge the positions on screen into them (drags are kept).
// Returns false when the response was dropped because something moved or saved
// meanwhile; the caller then merges again on the next poll.
async function reloadModels(): Promise<boolean> {
  const before = new Set(Object.keys(positions.value[OVERVIEW] ?? {}));
  const version = localVersion;
  const data = await mergeDiagrams(positions.value);
  if (version !== localVersion || draggingBox.value) return false;
  apply(data, { initial: false });
  const after = new Set(Object.keys(positions.value[OVERVIEW] ?? {}));
  const added = [...after].filter((key) => !before.has(key)).length;
  const removed = [...before].filter((key) => !after.has(key)).length;
  const parts = [added && `${added} new`, removed && `${removed} removed`].filter(Boolean);
  if (parts.length) toast.add({ title: `Models changed: ${parts.join(", ")}`, icon: "i-lucide-refresh-cw" });
  return true;
}

async function poll(): Promise<void> {
  if (polling || saving.value || draggingBox.value || document.visibilityState !== "visible") return;
  if (!loaded.value) return;
  polling = true;
  try {
    const status = await fetchStatus();
    failedPolls = 0;
    serverGone.value = false;
    loadIssue.value = status.error;
    layoutChanged.value = status.revision !== revision.value;
    if (status.model !== model.value) {
      try {
        if (model.value === null || (await reloadModels())) model.value = status.model;
        mergeIssue.value = null;
      } catch (error) {
        mergeIssue.value = error instanceof Error ? error.message : String(error);
      }
    }
  } catch (error) {
    if (error instanceof Unreachable) {
      failedPolls += 1;
      serverGone.value = failedPolls >= 3;
    } else {
      // The server answered with an error (e.g. an unreadable layout file).
      failedPolls = 0;
      serverGone.value = false;
      loadIssue.value = error instanceof Error ? error.message : String(error);
    }
  } finally {
    polling = false;
  }
}

function onMove(key: string, position: Position): void {
  const name = current.value;
  positions.value = { ...positions.value, [name]: { ...positions.value[name], [key]: position } };
  moved.value = new Set([...moved.value, name]);
  edits[name] = (edits[name] ?? 0) + 1;
  localVersion += 1;
}

async function save(): Promise<void> {
  if (!loaded.value || saving.value || !saveable.value) return;
  saving.value = true;
  const editsAtSave = { ...edits };
  try {
    const outcome = await saveLayout(revision.value, positions.value);
    if (outcome.ok) {
      revision.value = outcome.revision;
      layoutChanged.value = false;
      localVersion += 1;
      moved.value = new Set([...moved.value].filter((name) => edits[name] !== editsAtSave[name]));
      newKeys.value = {};
      toast.remove(SAVE_ERROR);
      // The layout file now holds everything; only the SVGs may still lag behind.
      if (loaded.value) {
        loaded.value.pending = { placed: 0, diagrams: 0, dropped: 0, created: false, svgs: outcome.exportError ? 1 : 0 };
      }
      if (outcome.exportError) {
        // The layout is saved; the SVGs are not. Keep Save enabled to retry.
        pendingShown.value = true;
        toast.add({
          title: `Saved, but the SVG export failed: ${outcome.exportError}`,
          color: "warning",
          icon: "i-lucide-triangle-alert",
          duration: 0,
        });
      } else {
        pendingShown.value = false;
        toast.add({ title: `Saved to ${outcome.saved}`, color: "success", icon: "i-lucide-check" });
      }
    } else if (outcome.conflict && outcome.reason === "models") {
      // The files changed in the second before the next poll: catch up, keep the drags.
      await reloadModels().catch((error: unknown) => {
        mergeIssue.value = error instanceof Error ? error.message : String(error);
      });
      showError("The models changed while saving — updated, save again.");
    } else if (outcome.conflict) {
      showError(
        "The layout file changed since this page loaded (on disk or from another tab). Reload to get it — saving now would overwrite it.",
      );
    } else {
      showError(`Could not save: ${outcome.message}`);
    }
  } finally {
    saving.value = false;
  }
}

const downloading = ref(false);

async function download(): Promise<void> {
  if (!loaded.value || downloading.value) return;
  downloading.value = true;
  let outcome;
  try {
    outcome = await downloadSvg(current.value, positions.value[current.value]);
  } finally {
    downloading.value = false;
  }
  if (outcome.ok) return;
  showError(
    outcome.conflict
      ? "The models changed since this page loaded. Reload to get them, then download again."
      : `Could not download the SVG: ${outcome.message}`,
  );
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
    const status = await fetchStatus();
    const data = await fetchDiagrams();
    model.value = status.model;
    loadIssue.value = status.error;
    apply(data, { initial: true });
    pollTimer = window.setInterval(() => void poll(), POLL_MS);
    // An unknown name in the hash is replaced, so the URL names what is shown.
    if (hashDiagram() !== null) select(hashTarget());
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : String(error);
  }
});

onBeforeUnmount(() => {
  window.removeEventListener("keydown", onKey);
  window.removeEventListener("beforeunload", onBeforeUnload);
  window.removeEventListener("hashchange", onHashChange);
  window.clearInterval(pollTimer);
});
</script>

<template>
  <UApp>
    <div class="flex h-screen flex-col">
      <StudioToolbar :title="diagram?.label ?? 'Overview'" :dirty="dirty" :saveable="saveable" :saving="saving" :downloading="downloading" @save="save" @download="download" />
      <UAlert
        v-if="serverGone"
        title="erdify-studio is not running any more."
        color="error"
        variant="subtle"
        icon="i-lucide-plug-zap"
        class="rounded-none"
      />
      <UAlert
        v-if="loadIssue"
        :title="`${loadIssue} — showing the last good state.`"
        color="error"
        variant="subtle"
        icon="i-lucide-file-warning"
        class="rounded-none"
      />
      <UAlert
        v-if="mergeIssue"
        :title="`Could not update the diagram: ${mergeIssue}`"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        class="rounded-none"
      />
      <UAlert
        v-if="layoutChanged"
        title="The layout file changed on disk. Reload to get it — saving now would overwrite it."
        color="warning"
        variant="subtle"
        icon="i-lucide-triangle-alert"
        class="rounded-none"
      />
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
            @dragging="draggingBox = $event"
            @view="onView"
          />
        </main>
      </div>
    </div>
  </UApp>
</template>
