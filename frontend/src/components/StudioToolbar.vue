<script setup lang="ts">
defineProps<{
  title: string;
  dirty: boolean;
  saveable: boolean;
  saving: boolean;
  downloading: boolean;
  // The canvas shows colours from the colour panel, not pyproject.toml's.
  previewing: boolean;
}>();
defineEmits<{ save: []; download: []; colours: [] }>();

const isMac = /Mac|iPhone|iPad/.test(navigator.platform);
</script>

<template>
  <header class="flex items-center gap-3 border-b border-default px-4 py-2">
    <img src="/favicon.svg" alt="" class="size-6 shrink-0" />
    <span class="font-semibold">erdify-studio · {{ title }}</span>
    <UBadge v-if="dirty" color="warning" variant="subtle" icon="i-lucide-circle-dot" label="Unsaved changes" />
    <UButton
      class="ml-auto"
      icon="i-lucide-palette"
      :label="previewing ? 'Colours · preview' : 'Colours'"
      :color="previewing ? 'primary' : 'neutral'"
      :variant="previewing ? 'soft' : 'outline'"
      :title="previewing ? 'The canvas shows a colour preview; Download SVG uses pyproject.toml' : undefined"
      @click="$emit('colours')"
    />
    <UButton
      icon="i-lucide-download"
      label="Download SVG"
      color="neutral"
      variant="outline"
      :loading="downloading"
      :disabled="downloading"
      @click="$emit('download')"
    />
    <UButton
      icon="i-lucide-save"
      :label="`Save  ${isMac ? '⌘S' : 'Ctrl+S'}`"
      :loading="saving"
      :disabled="!saveable || saving"
      @click="$emit('save')"
    />
  </header>
</template>
