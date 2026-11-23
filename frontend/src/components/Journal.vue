<template>
  <div>
    <div class="panel">
      <h3>📚 Journal des hypothèses (M13)</h3>
      <div class="sub" style="margin-bottom:10px">
        Mémoire scientifique : chaque hypothèse testée conserve ses conclusions,
        y compris rejetées et non concluantes — pour ne jamais refaire le même
        test ni réinterpréter un échec en découverte.
      </div>
      <table class="data mb0" v-if="hypotheses?.length">
        <tr><th>Code</th><th>Hypothèse</th><th>Statut</th><th>Findings</th>
            <th>✔</th><th>✘</th><th>?</th><th>Dernier</th></tr>
        <tr v-for="h in hypotheses" :key="h.hypothesis_id">
          <td class="mono">{{ h.code }}</td>
          <td style="max-width:420px">{{ h.title }}<div class="sub">{{ h.statement }}</div></td>
          <td><span class="badge" :class="statusClass(h.status)">{{ h.status }}</span></td>
          <td class="mono">{{ h.findings }}</td>
          <td class="mono">{{ h.supported }}</td>
          <td class="mono">{{ h.rejected }}</td>
          <td class="mono">{{ h.inconclusive }}</td>
          <td class="mono">{{ h.last_finding?.slice(0, 10) ?? '—' }}</td>
        </tr>
      </table>
      <div v-else class="sub">Aucune hypothèse enregistrée.</div>
    </div>

    <div class="panel">
      <h3>Conclusions ({{ findings?.length ?? 0 }})</h3>
      <table class="data mb0" v-if="findings?.length">
        <tr><th>Date</th><th>Hypothèse</th><th>Statut</th><th>Conclusion</th></tr>
        <tr v-for="f in findings" :key="f.finding_id">
          <td class="mono">{{ f.created_at?.slice(0, 10) }}</td>
          <td>{{ f.hypothesis }}</td>
          <td><span class="badge" :class="statusClass(f.status)">{{ f.status }}</span></td>
          <td style="max-width:520px">{{ f.conclusion }}</td>
        </tr>
      </table>
      <div v-else class="sub">Aucune conclusion enregistrée.</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { useFetch } from '../useFetch'

const { data: hypotheses } = useFetch<any[]>('/api/hypotheses')
const { data: findings } = useFetch<any[]>('/api/findings')

function statusClass(s: string) {
  return s === 'SUPPORTED' ? 'badge-ok'
    : s === 'REJECTED' ? 'badge-err'
    : s === 'INCONCLUSIVE' ? 'badge-warn' : ''
}
</script>
