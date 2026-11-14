<template>
  <div class="panel">
    <h3>🏆 Candidats par jeu — modèles préconisés</h3>
    <div class="sub" style="margin-bottom:10px">
      Un modèle n'est préconisé que s'il survit la correction FDR (q &lt; 0.10)
      <b>et</b> reste positif en out-of-sample. « Aucun modèle démontré » est un
      résultat valide — pas un échec.
    </div>
    <div class="filters">
      <select v-model.number="top" @change="load">
        <option :value="5">Top 5 jeux</option>
        <option :value="8">Top 8 jeux</option>
        <option :value="15">Top 15 jeux</option>
      </select>
      <button @click="load" :disabled="loading">{{ loading ? 'calcul…' : 'Recalculer' }}</button>
      <span v-if="loading" class="badge-warn">première évaluation ~1 min (walk-forward × modèles)</span>
    </div>
    <div v-if="error" class="badge-err">{{ error }}</div>
    <table class="data mb0" v-else-if="rows.length">
      <tr><th>Jeu</th><th>Candidat préconisé</th><th>Verdict</th>
          <th>Lift WF</th><th>q FDR</th><th>Lift OOS</th><th>Robustesse</th></tr>
      <tr v-for="r in rows" :key="r.game">
        <td>{{ r.game }}</td>
        <td class="mono" :class="r.candidate ? 'badge-ok' : ''">{{ r.candidate ?? '—' }}</td>
        <td class="sub">{{ r.verdict }}</td>
        <td class="mono">{{ pct(r.best_raw?.lift_wf) }}</td>
        <td class="mono">{{ r.best_raw?.q_fdr ?? '—' }}</td>
        <td class="mono">{{ pct(r.best_raw?.lift_oos) }}</td>
        <td class="mono">{{ r.best_raw?.robustness ?? '—' }}/100</td>
      </tr>
    </table>
    <div v-else class="sub">Aucun jeu avec assez de tirages.</div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api'

const top = ref(8)
const rows = ref<any[]>([])
const loading = ref(false)
const error = ref('')

function pct(x?: number) { return x == null ? '—' : (x > 0 ? '+' : '') + x + ' %' }

async function load() {
  loading.value = true; error.value = ''
  try {
    const res = await api.get('/api/lab/candidates', { params: { top: top.value }, timeout: 300000 })
    if (res.data.error) error.value = res.data.error
    else rows.value = res.data.candidates ?? []
  } catch (e: any) {
    error.value = e.response?.data?.error || e.message
  } finally { loading.value = false }
}
onMounted(load)
</script>
