<template>
  <h2 class="page-title">🏠 Vue d'ensemble</h2>
  <div v-if="err" class="panel"><span class="badge-err">{{ err }}</span></div>

  <div class="cards" v-if="o">
    <div class="card"><div class="label">Tirages validés</div>
      <div class="value gold">{{ o.settled_draws.toLocaleString() }}</div>
      <div class="sub">{{ o.first_draw }} → {{ o.last_draw }}</div></div>
    <div class="card"><div class="label">Types de tirages</div>
      <div class="value">{{ o.draw_types }}</div></div>
    <div class="card"><div class="label">Prédictions</div>
      <div class="value">{{ o.predictions_total }}</div>
      <div class="sub">{{ o.scored }} scorées · {{ o.pending }} en vol</div></div>
    <div class="card"><div class="label">Alertes ouvertes</div>
      <div class="value" :class="o.open_alerts ? 'red' : 'green'">{{ o.open_alerts }}</div></div>
    <div class="card"><div class="label">Échecs jobs 24h</div>
      <div class="value" :class="o.failed_24h ? 'red' : 'green'">{{ o.failed_24h }}</div></div>
    <div class="card"><div class="label">Dernier job</div>
      <div class="value mono" style="font-size:13px">{{ fmt(o.last_job_run) }}</div></div>
  </div>

  <div class="panel" v-if="alerts?.length">
    <h3>🚨 Alertes ouvertes</h3>
    <div v-for="a in alerts" :key="a.alert_id"
         class="alert-line" :class="a.severity === 'CRITICAL' ? 'alert-critical' : 'alert-warning'">
      <b>{{ a.code }}</b> — {{ a.details?.count ?? '' }}
      <span class="mono" style="float:right">{{ fmt(a.raised_at) }}</span>
      <div class="mono" style="font-size:11px;color:var(--muted)">{{ a.dedupe_key }}</div>
    </div>
  </div>

  <div class="panel">
    <h3>Derniers tirages</h3>
    <table class="data mb0" v-if="draws?.length">
      <tr><th>Date</th><th>Type</th><th>Statut</th><th>Numéros gagnants</th></tr>
      <tr v-for="d in draws" :key="d.draw_id">
        <td class="mono">{{ d.scheduled_date }}</td>
        <td>{{ d.draw_type }}</td>
        <td><span :class="d.status === 'SETTLED' ? 'badge-ok' : 'badge-warn'">{{ d.status }}</span></td>
        <td><span v-for="n in (d.winning_numbers || [])" :key="n" class="num-ball">{{ n }}</span></td>
      </tr>
    </table>
    <div v-else class="sub">Aucun tirage récent.</div>
  </div>
</template>

<script setup lang="ts">
import { useFetch } from '../useFetch'
const { data: o, error: err } = useFetch('/api/overview')
const { data: draws } = useFetch<any[]>('/api/draws')
const { data: alerts } = useFetch<any[]>('/api/alerts')
function fmt(s?: string) { return s ? s.replace('T', ' ').slice(0, 19) : '—' }
</script>
