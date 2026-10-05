<template>
  <div class="panel">
    <h3>🔁 Replay walk-forward — chaque modèle rejoue le tirage</h3>
    <div class="sub" style="margin-bottom:10px">
      Choisis un jeu et une date : les modèles ne voient <b>que l'historique antérieur</b>
      au tirage — reproductible, sans fuite temporelle. Résultat simulé, pas un gain réel.
    </div>
    <div class="filters">
      <input type="date" v-model="date" :max="today" @change="load" />
    </div>
    <div class="chips">
      <button v-for="t in types" :key="t.code + t.display_name" class="chip"
              :class="{ active: drawType === t.display_name }"
              @click="drawType = t.display_name; load()">
        {{ t.display_name }} <span class="chip-n">{{ t.settled_draws }}</span>
      </button>
    </div>

    <div v-if="loading" class="sub">Chargement…</div>
    <div v-else-if="error" class="badge-err">{{ error }}</div>
    <template v-else-if="replay">
      <div class="replay-cards">
        <div class="rcard">
          <div class="rlabel">Jeu sélectionné</div>
          <div class="rvalue gold">{{ replay.draw_type }}</div>
          <div class="sub">{{ replay.history_draws }} tirages d'historique</div>
        </div>
        <div class="rcard">
          <div class="rlabel">Tirage réel inspecté ({{ replay.date }})</div>
          <div v-if="replay.winning_numbers" class="rballs">
            <span v-for="(n, i) in replay.winning_numbers" :key="i" class="num-ball actual">{{ n }}</span>
          </div>
          <div v-else class="sub">Pas de tirage enregistré ce jour pour ce jeu.</div>
        </div>
        <div class="rcard">
          <div class="rlabel">Cible</div>
          <div class="rvalue">rejeu walk-forward</div>
          <div class="sub">tous les modèles : mêmes conditions, seeds figées</div>
        </div>
      </div>

      <table class="data mb0" v-if="replay.models?.length">
        <tr>
          <th>Modèle</th><th>Numéros prédits</th><th>Hits</th>
          <th>Numéros touchés</th><th v-for="v in turboCols" :key="v">{{ v.replace('turbo_','Turbo ') }}</th>
        </tr>
        <tr v-for="m in replay.models" :key="m.model_code"
            :class="{ 'baseline-row': m.model_code === 'null_model_benchmark' }">
          <td class="mono">{{ m.model_code }} <span class="sub">v{{ m.model_version }}</span></td>
          <td><span v-for="(n, i) in m.predicted" :key="i" class="num-ball"
                    :class="{ hit: m.hit_numbers?.includes(n) }">{{ n }}</span></td>
          <td class="mono" :class="m.hits > 0 ? 'badge-ok' : ''">
            {{ m.hits != null ? m.hits + '/' + m.predicted.length : '—' }}
          </td>
          <td><span v-for="n in m.hit_numbers ?? []" :key="n" class="num-ball actual">{{ n }}</span>
              <span v-if="!m.hit_numbers?.length" class="sub">—</span></td>
          <td v-for="v in turboCols" :key="v" class="mono" style="font-size:11px">
            <template v-if="m.turbo?.[v]">
              <span :class="m.turbo[v].hit ? 'badge-ok' : 'badge-err'">
                {{ m.turbo[v].hit ? 'WIN +' + fcfa(m.turbo[v].net) : fcfa(m.turbo[v].net) }}</span>
            </template><template v-else>—</template>
          </td>
        </tr>
      </table>
      <div class="sub" style="margin-top:8px">{{ replay.disclaimer }}</div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import api from '../api'

const turboCols = ['turbo_2', 'turbo_3', 'turbo_4', 'turbo_5']
const today = new Date().toISOString().slice(0, 10)
const date = ref(today)
const drawType = ref('')
const types = ref<any[]>([])
const replay = ref<any>(null)
const loading = ref(false)
const error = ref('')

function fcfa(x: number) { return Math.round(x).toLocaleString('fr-FR') + ' F' }

async function load() {
  if (!drawType.value || !date.value) return
  loading.value = true; error.value = ''
  try {
    const res = await api.get('/api/lab/replay', {
      params: { draw_type: drawType.value, date: date.value } })
    replay.value = res.data.error ? null : res.data
    if (res.data.error) error.value = res.data.error
  } catch (e: any) {
    error.value = e.response?.data?.error || e.message
    replay.value = null
  } finally { loading.value = false }
}

onMounted(async () => {
  try {
    const res = await api.get('/api/lab/draw-types')
    types.value = (res.data.data ?? []).filter((t: any) => t.settled_draws > 0)
    if (types.value.length) {
      drawType.value = types.value[0].display_name
      // dernière date avec tirage réel pour un premier affichage utile
      date.value = types.value[0].last_draw ?? today
      await load()
    }
  } catch { /* la vue reste vide, l'utilisateur choisit */ }
})
</script>

<style scoped>
.chips { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 14px; }
.chip {
  background: var(--panel-2); color: var(--muted); border: 1px solid var(--border);
  border-radius: 14px; padding: 4px 12px; cursor: pointer; font-size: 12px;
}
.chip:hover { color: var(--text); }
.chip.active { background: var(--gold); color: #111; font-weight: 700; border-color: var(--gold); }
.chip-n { opacity: 0.7; font-size: 10px; }
.replay-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin-bottom: 14px; }
.rcard { background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; padding: 12px; }
.rlabel { color: var(--muted); font-size: 11px; margin-bottom: 6px; }
.rvalue { font-size: 16px; font-weight: 700; }
.rvalue.gold { color: var(--gold-soft); }
.rballs { padding: 4px 0; }
.num-ball.hit { outline: 2px solid var(--green); }
.baseline-row td { opacity: 0.7; font-style: italic; }
</style>
