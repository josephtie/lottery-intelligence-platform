<template>
  <h2 class="page-title">🔬 Recherche</h2>

  <div class="tabbar">
    <div v-for="g in groups" :key="g.label" class="tabgroup">
      <span class="glabel">{{ g.label }}</span>
      <button v-for="t in g.tabs" :key="t.id" class="tab"
              :class="{ active: tab === t.id }" @click="tab = t.id">
        {{ t.label }}</button>
    </div>
  </div>
  <div class="tab-desc">{{ activeTab?.desc }}</div>

  <ReplayLab v-if="tab === 'replay'" :show5="true" />
  <LabMatrix v-else-if="tab === 'matrix'" />
  <LabCandidates v-else-if="tab === 'candidates'" />
  <ProspectiveH008 v-else-if="tab === 'prospective'" />
  <LabStructure v-else-if="tab === 'structure'" />
  <StructureMap v-else-if="tab === 'structuremap'" />
  <LabCallingImage v-else-if="tab === 'calling'" />
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
import { ref, computed } from 'vue'
import { useFetch } from '../useFetch'
import ReplayLab from '../components/ReplayLab.vue'
import LabMatrix from '../components/LabMatrix.vue'
import LabCandidates from '../components/LabCandidates.vue'
import ProspectiveH008 from '../components/ProspectiveH008.vue'
import LabStructure from '../components/LabStructure.vue'
import LabCallingImage from '../components/LabCallingImage.vue'
import StructureMap from '../components/StructureMap.vue'
import LabSimulation from '../components/LabSimulation.vue'
import GameProfiles from '../components/GameProfiles.vue'
import Journal from '../components/Journal.vue'

const groups = [
  { label: 'Preuve', tabs: [
    { id: 'candidates', label: '🏆 Y a-t-il un gagnant ?',
      desc: 'Le meilleur modèle de chaque jeu — ou le verdict honnête « aucun modèle démontré », qui est un résultat valable.' },
    { id: 'matrix', label: '📐 Qui tient ses promesses ?',
      desc: 'Tous les modèles rejouent les mêmes tirages et sont comparés au hasard. Un modèle n\'est « candidat » que s\'il fait mieux que le hasard de façon stable — pas sur un coup de chance.' },
    { id: 'prospective', label: '🔮 Prédictions en conditions réelles',
      desc: 'Des prédictions sont scellées AVANT le tirage et mesurées APRÈS. C\'est la seule preuve qui compte — impossible de tricher sur le futur.' },
    { id: 'profiles', label: '🧠 Historique par jeu',
      desc: 'Chaque jeu a son profil : semaine par semaine, jour par jour, quel modèle a été régulier — et lequel a juste eu de la chance.' },
  ]},
  { label: 'Structure du processus', tabs: [
    { id: 'structuremap', label: '�️ Carte de structure',
      desc: 'Le processus de tirage a-t-il une structure ? Fréquences fenêtrées, transitions 90×90, positions, retards, ruptures, saisonnalité, cross-game — chaque famille contre son null, FDR + OOS. INTERESTING ≠ prédictif.' },
    { id: 'structure', label: '🧬 Le tirage est-il normal ?',
      desc: 'Tests statistiques sur l\'historique : fréquences équilibrées ? mémoire entre tirages ? rupture ? Réponse honnête attendue : « compatible avec le hasard ».' },
    { id: 'calling', label: '🧲 Numéros appelés',
      desc: 'Hypothèses directionnelles : numéro image (57→75) et numéros « appelés » par proximité sur la grille. Chaque arête A→B est mesurée contre le hasard — une association n\'est jamais une promesse.' },
  ]},
  { label: 'Outils', tabs: [
    { id: 'replay', label: '🔁 Rejouer le passé',
      desc: 'Que prédisait chaque modèle pour un tirage déjà connu ? On rejoue la scène sans tricher : le modèle ne voit que les tirages d\'avant. Rien n\'est modifié.' },
    { id: 'simulation', label: '💰 Argent & portefeuilles',
      desc: 'Si on jouait vraiment : combien on miserait, ce qu\'on récupérerait, le risque de tout perdre. Et comment répartir les numéros entre grilles.' },
  ]},
  { label: 'Registre', tabs: [
    { id: 'journal', label: '📚 Carnet de recherche',
      desc: 'Toutes les hypothèses testées et leur verdict : confirmée, rejetée, ou pas encore tranchée. On ne répète pas deux fois la même erreur.' },
    { id: 'catalog', label: '📋 Catalogue',
      desc: 'L\'inventaire technique : modèles enregistrés, cohortes prospectives, datasets versionnés.' },
  ]},
]
const tabs = groups.flatMap(g => g.tabs)
const tab = ref('candidates')
const activeTab = computed(() => tabs.find(t => t.id === tab.value))

const { data: models } = useFetch<any[]>('/api/models')
const { data: datasets } = useFetch<any[]>('/api/datasets')
const { data: cohorts } = useFetch<any[]>('/api/cohorts')
</script>

<style scoped>
.tabbar { display: flex; gap: 14px; margin-bottom: 14px; flex-wrap: wrap; }
.tabgroup { display: flex; gap: 4px; align-items: center; }
.glabel {
  color: var(--muted); font-size: 10px; text-transform: uppercase;
  letter-spacing: .06em; margin-right: 4px; white-space: nowrap; opacity: .7;
}
.tab {
  background: var(--panel); color: var(--muted); border: 1px solid var(--border);
  border-radius: 6px 6px 0 0; padding: 8px 16px; cursor: pointer; font-size: 13px;
}
.tab:hover { color: var(--text); }
.tab.active { background: var(--gold); color: #111; font-weight: 700; border-color: var(--gold); }
.tab-desc {
  color: var(--muted); font-size: 12.5px; line-height: 1.45;
  padding: 8px 4px 14px; max-width: 900px;
}
.null-row td { opacity: 0.75; }
</style>
