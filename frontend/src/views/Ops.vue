<template>
  <h2 class="page-title">⚙️ Opérations</h2>

  <div class="cards" v-if="jobs">
    <div class="card"><div class="label">Runs 100 derniers</div>
      <div class="value">{{ jobs.length }}</div></div>
    <div class="card"><div class="label">Réussis</div>
      <div class="value green">{{ count('SUCCEEDED') }}</div></div>
    <div class="card"><div class="label">Échoués</div>
      <div class="value" :class="count('FAILED') + count('DEAD') ? 'red' : 'green'">
        {{ count('FAILED') + count('DEAD') }}</div></div>
    <div class="card"><div class="label">En file / cours</div>
      <div class="value">{{ count('QUEUED') + count('RUNNING') }}</div></div>
  </div>

  <div class="panel">
    <h3>Derniers runs de jobs</h3>
    <table class="data mb0" v-if="jobs?.length">
      <tr><th>Job</th><th>Statut</th><th>Créé</th><th>Durée</th><th>Détail</th></tr>
      <tr v-for="r in jobs" :key="r.job_run_id">
        <td class="mono">{{ r.code }}</td>
        <td><span :class="badge(r.status)">{{ r.status }}</span></td>
        <td class="mono">{{ fmt(r.created_at) }}</td>
        <td class="mono">{{ dur(r) }}</td>
        <td class="mono" style="font-size:11px;max-width:380px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"
            :title="r.last_error || JSON.stringify(r.details)">
          {{ r.last_error ?? JSON.stringify(r.details ?? {}).slice(0, 120) }}</td>
      </tr>
    </table>
    <div v-else class="sub">Aucun run enregistré.</div>
  </div>

  <div class="panel" v-if="rec?.length">
    <h3>Réconciliation seconde source</h3>
    <div class="cards mb0" style="grid-template-columns:repeat(auto-fill,minmax(150px,1fr))">
      <div class="card" v-for="s in rec" :key="s.outcome">
        <div class="label">{{ s.outcome }}</div>
        <div class="value" :class="s.outcome === 'MATCH' ? 'green' : 'red'">{{ s.n }}</div>
        <div class="sub">{{ fmt(s.latest) }}</div></div>
    </div>
    <table class="data" v-if="recRows?.length" style="margin-top:10px">
      <tr><th>Date</th><th>Tirage</th><th>Verdict</th><th>Primaire</th><th>Secondaire</th></tr>
      <tr v-for="c in recRows.slice(0, 20)" :key="c.comparison_id">
        <td class="mono">{{ c.draw_date }}</td><td>{{ c.draw_name }}</td>
        <td><span :class="c.outcome === 'MATCH' ? 'badge-ok' : 'badge-err'">{{ c.outcome }}</span></td>
        <td class="mono">{{ c.primary_numbers?.join(',') ?? '—' }}</td>
        <td class="mono">{{ c.secondary_numbers?.join(',') }}</td>
      </tr>
    </table>
  </div>
</template>

<script setup lang="ts">
import { useFetch } from '../useFetch'
const { data: jobs } = useFetch<any[]>('/api/jobs')
const { data: rec } = useFetch<any[]>('/api/reconciliation/summary')
const { data: recRows } = useFetch<any[]>('/api/reconciliation')
function count(s: string) { return (jobs.value ?? []).filter(j => j.status === s).length }
function badge(s: string) {
  return s === 'SUCCEEDED' ? 'badge-ok' : (s === 'FAILED' || s === 'DEAD') ? 'badge-err' : 'badge-warn'
}
function fmt(s?: string) { return s ? s.replace('T', ' ').slice(5, 16) : '—' }
function dur(r: any) {
  if (!r.started_at || !r.finished_at) return '—'
  return ((new Date(r.finished_at).getTime() - new Date(r.started_at).getTime()) / 1000).toFixed(1) + 's'
}
</script>
