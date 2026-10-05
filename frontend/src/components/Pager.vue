<template>
  <div class="pager-wrap" v-if="total > perPage">
    <button class="pager" :disabled="page <= 1" @click="go(page - 1)">‹ Préc.</button>
    <span class="pager-info mono">
      {{ firstItem }}–{{ lastItem }} / {{ total.toLocaleString('fr-FR') }}
      <template v-if="label"> · {{ label }}</template>
    </span>
    <button class="pager" :disabled="page >= pages" @click="go(page + 1)">Suiv. ›</button>
    <select class="pager-size mono" :value="perPage" @change="resize($event)">
      <option v-for="s in sizes" :key="s" :value="s">{{ s }} / page</option>
    </select>
  </div>
  <div class="pager-wrap subtle" v-else-if="total > 0">
    <span class="pager-info mono">{{ total.toLocaleString('fr-FR') }}<template v-if="label"> · {{ label }}</template></span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  total: number
  perPage: number
  page: number
  label?: string
}>(), { label: '' })

const emit = defineEmits(['update:page', 'update:perPage'])

const sizes = [20, 50, 100, 200]

const pages = computed(() => Math.ceil(props.total / props.perPage))
const firstItem = computed(() => (props.page - 1) * props.perPage + 1)
const lastItem = computed(() => Math.min(props.page * props.perPage, props.total))

function go(p: number) {
  const clamped = Math.min(Math.max(1, p), pages.value)
  emit('update:page', clamped)
}

function resize(e: Event) {
  const v = Number((e.target as HTMLSelectElement).value)
  emit('update:perPage', v)
  emit('update:page', 1)
}
</script>

<style scoped>
.pager-wrap { display: flex; align-items: center; gap: 10px; margin-top: 10px; flex-wrap: wrap; }
.pager-wrap.subtle { margin-top: 6px; }
.pager-info { color: var(--muted); font-size: 12px; }
.pager-size {
  background: var(--bg, #1b1e24); color: var(--text, #eee); border: 1px solid var(--border, #333);
  border-radius: 4px; padding: 2px 6px; font-size: 12px;
}
button.pager { min-width: 0; }
</style>
