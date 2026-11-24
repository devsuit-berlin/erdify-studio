<script setup lang="ts">
// The colour panel (#68): try diagram colours on the canvas without writing anything,
// then copy them as the [tool.erdify-studio.colors] table. The server resolves the
// palette and formats the TOML (POST /api/colors); this component only holds the edits.
import { computed, onBeforeUnmount, ref, watch } from "vue";

import { previewColors, type ColorConfig, type ColorKey, type ColorsJson } from "../api";

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
const invalid = ref<Partial<Record<ColorKey, string>>>({});
const isDark = ref(false);

const changed = computed(() => Object.keys(edits.value).length > 0);
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

let timer: ReturnType<typeof setTimeout> | undefined;
let request = 0;

function schedule(): void {
  clearTimeout(timer);
  timer = setTimeout(refresh, 150);
}

async function refresh(): Promise<void> {
  const mine = ++request;
  try {
    const result = await previewColors({ ...props.config, ...edits.value });
    if (mine !== request) return; // a newer edit is on its way
    last.value = result;
    invalid.value = {};
    emit("preview", changed.value ? result.colors : null);
  } catch (e) {
    if (mine !== request) return;
    // Keep the last good preview; mark the key the server named.
    const message = e instanceof Error ? e.message : String(e);
    const key = (Object.keys(JSON_KEY) as ColorKey[]).find((k) => message.includes(`'${k}'`));
    invalid.value = key ? { [key]: message } : {};
  }
}

function set(key: ColorKey, text: string): void {
  edits.value = { ...edits.value, [key]: text.trim() };
  schedule();
}

/** Back to the config's value (or the default, for a key the config doesn't set). */
function clear(key: ColorKey): void {
  const next = { ...edits.value };
  delete next[key];
  if (key in props.config) next[key] = null;
  edits.value = next;
  schedule();
}

function reset(): void {
  edits.value = {};
  invalid.value = {};
  last.value = null;
  emit("preview", null);
  if (props.open) void refresh();
}

async function copy(): Promise<void> {
  if (!last.value) await refresh();
  if (!last.value) return;
  try {
    await navigator.clipboard.writeText(last.value.toml);
    toast.add({ title: "Copied the colours as TOML", description: "Paste them into pyproject.toml.", icon: "i-lucide-clipboard-check" });
  } catch {
    toast.add({ title: "Could not copy to the clipboard", color: "error", icon: "i-lucide-circle-alert" });
  }
}

watch(
  () => props.open,
  (open) => {
    if (!open) return;
    isDark.value = document.documentElement.classList.contains("dark");
    void refresh();
  },
);
// The config's colours changed (pyproject.toml was edited): its values take over.
watch(() => JSON.stringify(props.config), reset);

onBeforeUnmount(() => clearTimeout(timer));
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
            :color="invalid[key] ? 'error' : undefined"
            :highlight="!!invalid[key]"
            :title="invalid[key]"
            @update:model-value="(v: string | number) => set(key, String(v))"
          />
          <span v-if="isDefault(key)" class="text-xs text-dimmed">default</span>
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
