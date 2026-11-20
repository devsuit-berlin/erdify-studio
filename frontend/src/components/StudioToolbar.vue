<script setup lang="ts">
defineProps<{ dirty: boolean; saving: boolean }>();
defineEmits<{ save: [] }>();

const isMac = /Mac|iPhone|iPad/.test(navigator.platform);
</script>

<template>
  <header class="flex items-center gap-3 border-b border-default px-4 py-2">
    <span class="font-semibold">erdify-studio · Overview</span>
    <UBadge v-if="dirty" color="warning" variant="subtle" icon="i-lucide-circle-dot" label="Unsaved changes" />
    <UButton
      class="ml-auto"
      icon="i-lucide-save"
      :label="`Save  ${isMac ? '⌘S' : 'Ctrl+S'}`"
      :loading="saving"
      :disabled="!dirty || saving"
      @click="$emit('save')"
    />
  </header>
</template>
