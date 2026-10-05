<template>
  <h2 class="page-title">🔬 Findings & expériences</h2>
  <div class="filters">
    <select v-model="status"><option value="">Tous statuts</option>
      <option>VALIDATED</option><option>REJECTED</option><option>INCONCLUSIVE</option></select>
  </div>
  <div v-if="err" class="panel"><span class="badge-err">{{ err }}</span></div>
  <div class="panel" v-for="f in filtered" :key="f.finding_id">
    <h3 style="display:flex;justify-content:space-between">
      <span>{{ f.hypothesis }}</span>
      <span :class="badge(f.status)">{{ f.status }}</span></h3>
    <div style="white-space:pre-wrap;font-size:13px">{{ f.conclusion }}</div>
    <div class="mono" style="font-size:11px;color:var(--muted);margin-top:8px">
      {{ fmt(f.created_at) }} · evidence: {{ JSON.stringify(f.evidence ?? {}).slice(0, 300) }}</div>
  </div>
  <div v-if="!filtered.length && !loading" class="panel"><span class="sub">Aucun finding.</span></div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useFetch } from '../useFetch'
const { data: findings, loading, error: err } = useFetch<any[]>('/api/findings')
const status = ref('')
const filtered = computed(() => (findings.value ?? []).filter(f => !status.value || f.status === status.value))
function badge(s: string) {
  return s === 'VALIDATED' ? 'badge-ok' : s === 'REJECTED' ? 'badge-err' : 'badge-warn'
}
function fmt(s?: string) { return s ? s.slice(0, 10) : '—' }
</script>
