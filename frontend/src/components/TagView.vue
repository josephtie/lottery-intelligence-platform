<template>
  <div class="tagview" v-if="options.length">
    <span class="tv-label mono">{{ label }} :</span>
    <button v-for="o in options" :key="o.value"
            :class="['tagchip', isActive(o.value) ? 'on' : '']"
            :style="isActive(o.value) ? (activeColor ? `background:${activeColor}22;border-color:${activeColor};color:${activeColor}` : '') : ''"
            @click="toggle(o.value)">
      <span v-if="o.emoji" class="tv-emoji">{{ o.emoji }}</span>{{ o.label }}
    </button>
    <button v-if="anyActive" class="tagclear" @click="$emit('clear')">✕</button>
  </div>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  label?: string
  options: { value: string, label: string, emoji?: string }[]
  modelValue: string[]
  activeColor?: string
}>(), { label: '', activeColor: '' })

const emit = defineEmits(['update:modelValue', 'clear'])

function isActive(v: string) { return props.modelValue.includes(v) }
function anyActive() { return props.modelValue.length > 0 }
function toggle(v: string) {
  const cur = props.modelValue.includes(v)
    ? props.modelValue.filter(x => x !== v)
    : [...props.modelValue, v]
  // mono-sélection si l'utilisateur veut basculer en exclusif ? Non: multi par défaut
  emit('update:modelValue', cur)
}
</script>

<style scoped>
.tagview { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin: 8px 0; }
.tv-label { color: var(--muted); font-size: 11px; margin-right: 2px; }
.tv-emoji { margin-right: 3px; }
.tagchip {
  background: transparent; border: 1px solid var(--border, #333); color: var(--muted);
  border-radius: 12px; padding: 3px 10px; font-size: 12px; cursor: pointer;
  transition: all .15s;
}
.tagchip:hover { color: var(--text); border-color: var(--muted); }
.tagchip.on {
  background: rgba(230, 180, 85, 0.12); border-color: var(--gold, #e6b455);
  color: var(--gold, #e6b455); font-weight: 600;
}
.tagclear {
  background: transparent; border: none; color: var(--red, #f56c6c);
  cursor: pointer; font-size: 13px; padding: 2px 6px;
}
</style>
