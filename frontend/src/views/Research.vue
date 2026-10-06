<template>
  <h2 class="page-title">🧪 Laboratoire de recherche</h2>

  <div class="tabbar">
    <button v-for="t in tabs" :key="t.id" class="tab"
            :class="{ active: tab === t.id }" @click="tab = t.id">
      {{ t.label }}</button>
  </div>

  <ReplayLab v-if="tab === 'replay'" :show5="true" />
  <LabMatrix v-else-if="tab === 'matrix'" />
  <LabCandidates v-else-if="tab === 'candidates'" />
  <ProspectiveH008 v-else-if="tab === 'prospective'" />
  <LabStructure v-else-if="tab === 'structure'" />
  <LabSimulation v-else-if="tab === 'simulation'" />
  <GameProfiles v-else-if="tab === 'profiles'" />
  <Journal v-else-if="tab === 'journal'" />

  <template v-else>
    <div class="panel">
      <h3>Cohortes prospectives</h3>
      <table class="data mb0" v-if="cohorts?.length">
        <tr><th>Code</th><th>Version</th><th>Membres</th><th>Définition</th><th>Depuis</th></tr>
        <tr v-for="c in cohorts" :key="c.cohort_version_id">
          <td class="mono">{{ c.code }}</td><td>v{{ c.version }}</td><td>{{ c.members }}</td>
          <td class="mono" style="font-size:11px;max-width:420px;overflow:hidden;text-overflow:ellipsis">
            {{ JSON.stringify(c.definition) }}</td>
          <td class="mono">{{ c.effective_from }}</td>
        </tr>
      </table>
      <div v-else class="sub">Aucune cohorte enregistrée.</div>
    </div>

    <div class="panel">
      <h3>Modèles ({{ models?.length ?? 0 }} versions)</h3>
      <table class="data mb0" v-if="models?.length">
        <tr><th>Code</th><th>v</th><th>Famille</th><th>Définition</th><th>Prédictions</th><th>Soldées</th></tr>
        <tr v-for="m in models" :key="m.code + m.version"
            :class="{ 'null-row': m.code === 'null_model_benchmark' }">
          <td class="mono">{{ m.code }}
            <span v-if="m.code === 'null_model_benchmark'" class="badge-warn" title="référence aléatoire">baseline</span></td>
          <td>{{ m.version }}</td><td>{{ m.family }}</td>
          <td class="mono" style="font-size:11px">{{ JSON.stringify(m.definition) }}</td>
          <td>{{ m.predictions }}</td><td>{{ m.settled }}</td>
        </tr>
      </table>
    </div>

    <div class="panel">
      <h3>Datasets versionnés</h3>
      <table class="data mb0" v-if="datasets?.length">
        <tr><th>Code</th><th>Version</th><th>Cutoff</th><th>Membres</th><th>Manifeste</th></tr>
        <tr v-for="d in datasets" :key="d.code + d.version_number">
          <td class="mono">{{ d.code }}</td><td>v{{ d.version_number }}</td>
          <td class="mono">{{ d.cutoff_at }}</td><td>{{ d.members.toLocaleString() }}</td>
          <td class="mono" style="font-size:11px">{{ d.manifest_sha256?.slice(0, 16) }}…</td>
        </tr>
      </table>
    </div>
  </template>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useFetch } from '../useFetch'
import ReplayLab from '../components/ReplayLab.vue'
import LabMatrix from '../components/LabMatrix.vue'
import LabCandidates from '../components/LabCandidates.vue'
import ProspectiveH008 from '../components/ProspectiveH008.vue'
import LabStructure from '../components/LabStructure.vue'
import LabSimulation from '../components/LabSimulation.vue'
import GameProfiles from '../components/GameProfiles.vue'
import Journal from '../components/Journal.vue'

const tabs = [
  { id: 'replay', label: '🔁 Prédictions par modèle' },
  { id: 'matrix', label: '📐 Matrice de performance' },
  { id: 'candidates', label: '🏆 Candidats par jeu' },
  { id: 'prospective', label: '🔮 Prospectif multi-modèles (H008)' },
  { id: 'structure', label: '🧬 Structure des tirages' },
  { id: 'simulation', label: '💰 Simulation & Couverture' },
  { id: 'profiles', label: '🧠 Profils des jeux' },
  { id: 'journal', label: '📚 Journal' },
  { id: 'catalog', label: '� Catalogue' },
]
const tab = ref('replay')

const { data: models } = useFetch<any[]>('/api/models')
const { data: datasets } = useFetch<any[]>('/api/datasets')
const { data: cohorts } = useFetch<any[]>('/api/cohorts')
</script>

<style scoped>
.tabbar { display: flex; gap: 4px; margin-bottom: 14px; flex-wrap: wrap; }
.tab {
  background: var(--panel); color: var(--muted); border: 1px solid var(--border);
  border-radius: 6px 6px 0 0; padding: 8px 16px; cursor: pointer; font-size: 13px;
}
.tab:hover { color: var(--text); }
.tab.active { background: var(--gold); color: #111; font-weight: 700; border-color: var(--gold); }
.null-row td { opacity: 0.75; }
</style>
