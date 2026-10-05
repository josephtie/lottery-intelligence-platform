<template>
  <h2 class="page-title">🧪 Laboratoire de recherche</h2>

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

<script setup lang="ts">
import { useFetch } from '../useFetch'
const { data: models } = useFetch<any[]>('/api/models')
const { data: datasets } = useFetch<any[]>('/api/datasets')
const { data: cohorts } = useFetch<any[]>('/api/cohorts')
</script>

<style scoped>
.null-row td { opacity: 0.75; }
</style>
