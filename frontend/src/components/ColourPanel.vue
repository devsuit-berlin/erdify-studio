<script setup lang="ts">
// The colour panel (#68): try diagram colours on the canvas without writing anything,
// then copy them as the [tool.erdify-studio.colors] table. The server resolves the
// palette and formats the TOML (POST /api/colors); this component only holds the edits.
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";

import { ColorPreviewError, previewColors, type ColorConfig, type ColorKey, type ColorsJson } from "../api";

const props = defineProps<{ open: boolean; config: ColorConfig; resolved: ColorsJson }>();
const emit = defineEmits<{ "update:open": [boolean]; preview: [ColorsJson | null] }>();

const toast = useToast();

const GROUPS: { title: string; keys: { key: ColorKey; label: string }[] }[] = [
  {
    title: "Brand",
    keys: [
      { key: "accent", label: "Accent" },
      { key: "header", label: "Header" },
      { key: "header_text", label: "Header text" },
      { key: "background", label: "Background" },
    ],
  },
  {
    title: "Details",
    keys: [
      { key: "text", label: "Text" },
      { key: "text_muted", label: "Muted text" },
      { key: "border", label: "Border" },
      { key: "border_strong", label: "Strong border" },
      { key: "background_muted", label: "Muted background" },
    ],
  },
];
// The API's camelCase name of each key.
const JSON_KEY: Record<ColorKey, keyof ColorsJson> = {
  accent: "accent",
  header: "header",
  header_text: "headerText",
  background: "background",
  text: "text",
  text_muted: "textMuted",
  border: "border",
  border_strong: "borderStrong",
  background_muted: "backgroundMuted",
};
const HEX = /^#[0-9a-fA-F]{6}$/;

// The panel's changes: a value, or null to drop a key the config sets.
const edits = ref<Partial<Record<ColorKey, string | null>>>({});
// The last good response: the colours shown and the TOML to copy.
const last = ref<{ colors: ColorsJson; toml: string } | null>(null);
// The key the server rejected (its message); malformed edits are marked locally below.
const rejected = ref<Partial<Record<ColorKey, string>>>({});
// An error that names no key (e.g. the server is gone).
const failure = ref<string | null>(null);
const isDark = ref(document.documentElement.classList.contains("dark"));

const changed = computed(() => Object.keys(edits.value).length > 0);
// Edits that aren't #rrggbb yet (half-typed): kept out of the preview, so the other rows
// keep previewing, and marked here.
const malformed = computed(() => {
  const marks: Partial<Record<ColorKey, string>> = {};
  for (const [key, edit] of Object.entries(edits.value) as [ColorKey, string | null][]) {
    if (typeof edit === "string" && !HEX.test(edit)) marks[key] = `'${key}' must be a "#rrggbb" colour`;
  }
  return marks;
});
const invalid = computed(() => ({ ...rejected.value, ...malformed.value }));
const shown = computed(() => last.value?.colors ?? props.resolved);

function value(key: ColorKey): string {
  const edit = edits.value[key];
  if (typeof edit === "string") return edit;
  if (edit === null) return shown.value[JSON_KEY[key]];
  return props.config[key] ?? shown.value[JSON_KEY[key]];
}

/** Not set anywhere: the value shown is the default or derived one. */
function isDefault(key: ColorKey): boolean {
  return typeof edits.value[key] !== "string" && (edits.value[key] === null || !(key in props.config));
}

/** An unset header text follows the header (white or dark by contrast) once one is set. */
function isAutomatic(key: ColorKey): boolean {
  return key === "header_text" && !isDefault("header");
}

let timer: ReturnType<typeof setTimeout> | undefined;
let request = 0;

function schedule(): void {
  clearTimeout(timer);
  request++; // a response still on its way is for older edits
  timer = setTimeout(refresh, 150);
}

async function refresh(): Promise<void> {
  const mine = ++request;
  // Malformed edits stay out (a configured key keeps its value meanwhile).
  const valid = Object.fromEntries(
    Object.entries(edits.value).filter(([, v]) => v === null || HEX.test(v)),
  );
  const sent = { ...props.config, ...valid };
  try {
    const result = await previewColors(sent);
    if (mine !== request) return; // a newer edit is on its way
    last.value = result;
    rejected.value = {};
    failure.value = null;
    emit("preview", changed.value ? result.colors : null);
  } catch (e) {
    if (mine !== request) return;
    // Keep the last good preview; mark the key the server named, else show the message.
    const message = e instanceof Error ? e.message : String(e);
    // Only a key with a row can be marked; anything else shows as a message.
    const key = e instanceof ColorPreviewError && e.key && e.key in JSON_KEY ? e.key : undefined;
    rejected.value = key ? { [key]: message } : {};
    failure.value = key ? null : message;
  }
}

function set(key: ColorKey, text: string): void {
  edits.value = { ...edits.value, [key]: text.trim() };
  schedule();
}

/** One step back: an edit → the config's value (or the default); a configured key → unset. */
function clear(key: ColorKey): void {
  const next = { ...edits.value };
  if (key in next) delete next[key];
  else next[key] = null;
  edits.value = next;
  schedule();
}

/** Undo "unset" on a configured key: back to the config's value. */
function restore(key: ColorKey): void {
  const next = { ...edits.value };
  delete next[key];
  edits.value = next;
  schedule();
}

function reset(): void {
  clearTimeout(timer);
  request++; // drop a response still on its way
  edits.value = {};
  rejected.value = {};
  failure.value = null;
  last.value = null;
  emit("preview", null);
  if (props.open) void refresh();
}

async function copy(): Promise<void> {
  // Copy what the panel shows: send a pending edit first, and never copy past a red row.
  clearTimeout(timer);
  await refresh();
  const problem = Object.values(invalid.value)[0] ?? failure.value;
  if (problem || !last.value) {
    toast.add({
      title: "Fix the marked colours first",
      description: problem ?? undefined,
      color: "error",
      icon: "i-lucide-circle-alert",
    });
    return;
  }
  try {
    await navigator.clipboard.writeText(last.value.toml);
    toast.add({
      title: "Copied the colours as TOML",
      description: "Replace the [tool.erdify-studio.colors] table in pyproject.toml with it.",
      icon: "i-lucide-clipboard-check",
    });
  } catch {
    toast.add({ title: "Could not copy to the clipboard", color: "error", icon: "i-lucide-circle-alert" });
  }
}

watch(
  () => props.open,
  (open) => {
    if (open) void refresh();
  },
);
// The config's colours changed (pyproject.toml was edited): its values take over.
watch(() => JSON.stringify(props.config), reset);

// The dark-mode note follows the theme while the panel is open, too.
const observer = new MutationObserver(() => {
  isDark.value = document.documentElement.classList.contains("dark");
});
onMounted(() => observer.observe(document.documentElement, { attributes: true, attributeFilter: ["class"] }));

onBeforeUnmount(() => {
  clearTimeout(timer);
  observer.disconnect();
});
</script>

<template>
  <USlideover
    :open="open"
    side="right"
    :overlay="false"
    :modal="false"
    title="Colours"
    description="Try diagram colours on the canvas. Nothing is saved: copy them into pyproject.toml."
    @update:open="emit('update:open', $event)"
  >
    <template #body>
      <UAlert
        v-if="isDark"
        color="neutral"
        variant="subtle"
        icon="i-lucide-moon"
        title="The preview shows in light mode."
        class="mb-4"
      />
      <UAlert
        v-if="failure"
        color="error"
        variant="subtle"
        icon="i-lucide-circle-alert"
        :title="failure"
        class="mb-4"
      />
      <section v-for="group in GROUPS" :key="group.title" class="mb-6">
        <h3 class="mb-2 text-sm font-semibold text-muted">{{ group.title }}</h3>
        <div v-for="{ key, label } in group.keys" :key="key" class="mb-2 flex items-center gap-2">
          <UPopover>
            <button
              type="button"
              class="size-7 shrink-0 rounded border border-default"
              :style="{ background: HEX.test(value(key)) ? value(key) : 'transparent' }"
              :aria-label="`Pick ${label}`"
            />
            <template #content>
              <UColorPicker
                format="hex"
                class="p-2"
                :model-value="HEX.test(value(key)) ? value(key) : undefined"
                @update:model-value="(v: string | undefined) => v && set(key, v)"
              />
            </template>
          </UPopover>
          <span class="w-32 shrink-0 text-sm">{{ label }}</span>
          <UInput
            :model-value="value(key)"
            size="sm"
            class="w-28 font-mono"
            :class="{ 'opacity-60': isDefault(key) }"
            :aria-label="`${label} (hex)`"
            :color="invalid[key] ? 'error' : undefined"
            :highlight="!!invalid[key]"
            :title="invalid[key]"
            @update:model-value="(v: string | number) => set(key, String(v))"
          />
          <UButton
            v-if="edits[key] === null"
            icon="i-lucide-undo-2"
            size="xs"
            color="neutral"
            variant="ghost"
            :aria-label="`Restore ${label} from pyproject.toml`"
            @click="restore(key)"
          />
          <span v-else-if="isDefault(key)" class="text-xs text-dimmed">{{ isAutomatic(key) ? "automatic" : "default" }}</span>
          <UButton
            v-else
            icon="i-lucide-x"
            size="xs"
            color="neutral"
            variant="ghost"
            :aria-label="`Reset ${label}`"
            @click="clear(key)"
          />
        </div>
      </section>
    </template>
    <template #footer>
      <div class="flex w-full gap-2">
        <UButton label="Reset" color="neutral" variant="outline" :disabled="!changed" @click="reset" />
        <UButton class="ml-auto" icon="i-lucide-clipboard-copy" label="Copy TOML" @click="copy" />
      </div>
    </template>
  </USlideover>
</template>
