<template>
  <div class="reduced-field-page">
    <div class="page-header">
      <h2 class="page-title">🎯 Champs Réduits - Analyse Mathématique</h2>
      <span class="page-subtitle">Génération de tickets basés sur l'analyse des racines et positions</span>
    </div>

    <div v-if="err" class="error-banner">
      <el-alert type="error" :closable="false" show-icon>{{ err }}</el-alert>
    </div>

    <el-tabs v-model="activeTab" class="mode-tabs">
      <el-tab-pane label="🤖 Auto" name="auto">
        <div class="filters-bar">
          <el-date-picker
            v-model="targetDate"
            type="date"
            placeholder="Date du tirage"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 180px"
            @change="loadGamesForDate"
          />
          <el-select
            v-model="drawType"
            placeholder="Jeu du jour"
            filterable
            style="width: 220px"
            :disabled="!targetDate || gamesForDate.length === 0"
            @change="loadAnalysis"
          >
            <el-option
              v-for="g in gamesForDate"
              :key="g.draw_type_id"
              :label="g.display_name"
              :value="g.display_name"
            />
          </el-select>
          <el-select
            v-model="maxDraws"
            placeholder="Tirages à analyser"
            style="width: 180px"
          >
            <el-option label="10 tirages (1 jour)" :value="10" />
            <el-option label="22 tirages (2 jours)" :value="22" />
          </el-select>
          <el-switch
            v-model="withTurbo"
            active-text="Turbo (3e position)"
            inactive-text="Champ Réduit"
          />
          <el-button type="primary" @click="loadAnalysis" :loading="loading">
            Analyser
          </el-button>
        </div>
      </el-tab-pane>
      
      <el-tab-pane label="✋ Manuel" name="manual">
        <div class="filters-bar">
          <el-date-picker
            v-model="manualDate"
            type="date"
            placeholder="Date du jour"
            format="YYYY-MM-DD"
            value-format="YYYY-MM-DD"
            style="width: 180px"
            @change="loadManualGamesForDate"
          />
          <el-select
            v-model="manualDrawType"
            placeholder="Jeu du jour"
            filterable
            style="width: 220px"
            :disabled="!manualDate || manualGamesForDate.length === 0"
            @change="loadManualData"
          >
            <el-option
              v-for="g in manualGamesForDate"
              :key="g.draw_type_id"
              :label="g.display_name"
              :value="g.display_name"
            />
          </el-select>
          <el-button type="primary" @click="loadManualData" :loading="manualLoading">
            Charger les numéros joués
          </el-button>
        </div>
      </el-tab-pane>
    </el-tabs>

    <div v-if="activeTab === 'manual' && manualData" class="manual-section">
      <el-card v-if="dailyRootsData" class="manual-card">
        <template #header>
          <div class="card-header">
            <span>📊 Jeux du jour - Racines déjà jouées ({{ dailyRootsData.date }})</span>
          </div>
        </template>
        <div class="daily-roots-section">
          <div class="draws-table">
            <table class="data mb0">
              <tr>
                <th>Jeu</th>
                <th>Statut</th>
                <th>Résultat officiel</th>
                <th>Racines numériques</th>
              </tr>
              <tr v-for="game in dailyRootsData.predictions" :key="game.draw_id"
                  :class="{ 'current-game': game.draw_type === manualDrawType }">
                <td>{{ game.draw_type }}</td>
                <td><span :class="game.status === 'SETTLED' ? 'badge-ok' : 'badge-warn'">{{ game.status }}</span></td>
                <td>
                  <span v-if="game.actual_numbers">
                    <span v-for="n in game.actual_numbers" :key="n" class="num-ball actual">{{ n }}</span>
                  </span>
                  <span v-else class="sub">—</span>
                </td>
                <td>
                  <span v-if="game.actual_roots">
                    <span v-for="(root, i) in game.actual_roots" :key="i" class="num-ball root">{{ root }}</span>
                  </span>
                  <span v-else class="sub">—</span>
                </td>
              </tr>
            </table>
          </div>
        </div>
      </el-card>

      <el-card class="manual-card">
        <template #header>
          <div class="card-header">
            <span>🎯 Résultats et Racines du jour ({{ manualData.draw_type }})</span>
            <el-tag type="info">{{ manualData.total_draws }} tirages joués</el-tag>
          </div>
        </template>
        <div class="draws-table">
          <table class="data mb0">
            <tr>
              <th>Tirage</th>
              <th>Statut</th>
              <th>Résultat officiel</th>
              <th>Racines numériques</th>
            </tr>
            <tr v-for="draw in manualData.draws" :key="draw.sequence">
              <td class="mono">#{{ draw.sequence }}</td>
              <td><span :class="draw.status === 'SETTLED' ? 'badge-ok' : 'badge-warn'">{{ draw.status }}</span></td>
              <td>
                <span v-if="draw.numbers.length">
                  <span v-for="n in draw.numbers" :key="n" class="num-ball actual">{{ n }}</span>
                </span>
                <span v-else class="sub">—</span>
              </td>
              <td>
                <span v-if="draw.roots.length">
                  <span v-for="(root, i) in draw.roots" :key="i" class="num-ball root">{{ root }}</span>
                </span>
                <span v-else class="sub">—</span>
              </td>
            </tr>
          </table>
        </div>
      </el-card>

      <el-card class="manual-card">
        <template #header>
          <div class="card-header">
            <span>🚫 Numéros déjà joués aujourd'hui</span>
          </div>
        </template>
        <div class="played-numbers-grid">
          <div v-for="(numbers, root) in manualData.played_by_root" :key="root" class="root-group">
            <div class="root-header">
              <span class="root-badge">{{ root }}</span>
              <span class="root-count">{{ numbers.length }} joué(s)</span>
            </div>
            <div class="played-numbers">
              <span 
                v-for="num in numbers" 
                :key="num" 
                class="played-number"
                :class="{ 'played-3h-23h': manualData.played_numbers_3h_23h.includes(num) }"
              >
                {{ num }}
              </span>
            </div>
          </div>
        </div>
        
        <div v-if="manualData.in_time_window" class="time-window-info">
          <el-tag type="warning" size="small">
            ⏰ Ce jeu est dans la fenêtre 3h-23h (Heure: {{ manualData.draw_hour || 'N/A' }}h)
          </el-tag>
          <span class="time-window-count">
            {{ manualData.played_numbers_3h_23h.length }} numéros joués entre 3h-23h
          </span>
        </div>
      </el-card>

      <el-card class="manual-card">
        <template #header>
          <div class="card-header">
            <span>✋ Construire votre champ réduit</span>
          </div>
        </template>
        <div class="field-builder">
            
            <div class="field-step">
              <label>1. Choisir la racine de base (1re position) - Toutes les racines 0-8</label>
              <el-select v-model="selectedBaseRoot" placeholder="Choisir une racine" style="width: 200px">
                <el-option v-for="root in allRoots" :key="root" :label="`Racine ${root}`" :value="root" />
              </el-select>
              <div v-if="selectedBaseRoot !== null" class="root-preview">
                <span>Numéros de la racine {{ selectedBaseRoot }} ({{ getAvailableNumbers(selectedBaseRoot).length }} disponibles / {{ ROOT_FAMILIES[selectedBaseRoot].length }} total) - Cliquez pour choisir :</span>
                <div class="available-numbers clickable">
                  <span 
                    v-for="num in ROOT_FAMILIES[selectedBaseRoot]" 
                    :key="num" 
                    class="available-number clickable"
                    :class="{ 
                      selected: selectedBaseNumber === num,
                      played: manualData.played_numbers.includes(num),
                      'played-3h-23h': manualData.played_numbers_3h_23h.includes(num)
                    }"
                    @click="!manualData.played_numbers.includes(num) && selectBaseNumber(num)"
                  >
                    {{ num }}
                  </span>
                </div>
              </div>
            </div>
            
            <div class="field-step">
              <label>2. Choisir la racine pour les associés (2e position) - Racines non jouées</label>
              <el-select v-model="selectedAssociatedRoot" placeholder="Choisir une racine" style="width: 200px">
                <el-option v-for="root in availableRoots" :key="root" :label="`Racine ${root}`" :value="root" />
              </el-select>
              <div v-if="selectedAssociatedRoot !== null" class="root-preview">
                <span>Numéros disponibles pour les associés - Cliquez pour choisir (max 4) :</span>
                <div class="available-numbers clickable">
                  <span 
                    v-for="num in getAvailableNumbers(selectedAssociatedRoot)" 
                    :key="num" 
                    class="available-number clickable"
                    :class="{ 
                      selected: selectedAssociatedNumbers.includes(num),
                      'played-3h-23h': manualData.played_numbers_3h_23h.includes(num)
                    }"
                    @click="toggleAssociatedNumber(num)"
                  >
                    {{ num }}
                  </span>
                </div>
              </div>
            </div>
            
            <div class="field-step">
              <label>3. Votre champ réduit</label>
              <div class="field-preview">
                <div class="field-base">
                  <span class="field-label">Base :</span>
                  <span class="field-value">{{ selectedBaseNumber || 'Choisir un numéro' }}</span>
                </div>
                <div class="field-associated">
                  <span class="field-label">Associés ({{ selectedAssociatedNumbers.length }}/4) :</span>
                  <div class="associated-preview">
                    <span v-for="num in selectedAssociatedNumbers" :key="num" class="associated-number">{{ num }}</span>
                  </div>
                </div>
              </div>
              <el-button type="primary" @click="addManualField" :disabled="!canGenerateField">
                Ajouter à la liste
              </el-button>
            </div>
        </div>
      </el-card>
      
      <el-card v-if="manualFieldsList.length > 0" class="manual-fields-list-card">
        <template #header>
          <div class="card-header">
            <span>🎫 Vos Champs Réduits Manuels ({{ manualFieldsList.length }})</span>
            <el-button size="small" type="danger" @click="clearManualFields" :disabled="manualFieldsList.length === 0">
              Effacer tout
            </el-button>
          </div>
        </template>
        
        <div class="manual-fields-grid">
          <el-card v-for="(field, index) in manualFieldsList" :key="index" class="manual-field-item">
            <template #header>
              <div class="card-header">
                <span class="field-number">Champ #{{ index + 1 }}</span>
                <el-button size="small" type="danger" @click="removeManualField(index)">
                  Supprimer
                </el-button>
              </div>
            </template>
            
            <div class="manual-field-content">
              <div class="field-base-large">
                <div class="base-label">Base (1re position)</div>
                <div class="base-number-large">{{ field.base }}</div>
                <div class="base-root">Racine {{ field.base_root }}</div>
              </div>
              
              <div class="field-associated-large">
                <div class="associated-label">Associés (2e position)</div>
                <div class="associated-numbers-large">
                  <span v-for="num in field.associated" :key="num" class="number-ball-large">
                    {{ num }}
                  </span>
                </div>
                <div class="associated-roots-large">
                  Racines : {{ field.associated_roots.join(', ') }}
                </div>
              </div>
            </div>
          </el-card>
        </div>
      </el-card>
    </div>

    <div v-if="analysis" class="analysis-section">
      <el-card class="analysis-card">
        <template #header>
          <div class="card-header">
            <span>📊 Analyse Mathématique</span>
            <el-tag type="info">{{ analysis.draws_analyzed }} tirages analysés</el-tag>
          </div>
        </template>
        
        <div class="analysis-grid">
          <div class="analysis-item">
            <h4>Fréquences par Position</h4>
            <div class="frequency-list">
              <div v-for="(freq, pos) in analysis.patterns.position_1_frequency" :key="pos" class="freq-item">
                <span class="freq-number">{{ pos }}</span>
                <el-progress :percentage="Math.round(freq * 100 / analysis.patterns.total_draws)" :show-text="false" style="flex: 1" />
                <span class="freq-count">{{ freq }}</span>
              </div>
            </div>
          </div>
          
          <div class="analysis-item">
            <h4>Parité Position 2</h4>
            <div class="parity-stats">
              <div class="parity-item even">
                <span class="parity-label">Pair</span>
                <span class="parity-count">{{ analysis.patterns.position_2_parity.even }}</span>
              </div>
              <div class="parity-item odd">
                <span class="parity-label">Impair</span>
                <span class="parity-count">{{ analysis.patterns.position_2_parity.odd }}</span>
              </div>
            </div>
          </div>
          
          <div class="analysis-item">
            <h4>Racines les plus fréquentes</h4>
            <div class="root-list">
              <div v-for="(freq, root) in analysis.patterns.root_frequency" :key="root" class="root-item">
                <span class="root-badge">{{ root }}</span>
                <span class="root-count">{{ freq }}</span>
              </div>
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <div v-if="tickets.length" class="tickets-section">
      <h3>🎫 Tickets de Champ Réduit</h3>
      
      <div class="tickets-grid">
        <el-card v-for="(ticket, index) in tickets" :key="index" class="ticket-card">
          <template #header>
            <div class="ticket-header">
              <span class="ticket-strategy">{{ ticket.strategy }}</span>
              <el-tag :type="ticket.confidence > 0.5 ? 'success' : ticket.confidence > 0.3 ? 'warning' : 'info'" size="small">
                {{ (ticket.confidence * 100).toFixed(0) }}%
              </el-tag>
            </div>
          </template>
          
          <div class="ticket-content">
            <div class="ticket-base">
              <div class="base-label">Base (1re position)</div>
              <div class="base-number">{{ ticket.base }}</div>
              <div class="base-root">Racine {{ ticket.base_root }}</div>
            </div>
            
            <div class="ticket-associated">
              <div class="associated-label">Associés (2e position)</div>
              <div class="associated-numbers">
                <span v-for="num in ticket.associated" :key="num" class="number-ball">
                  {{ num }}
                </span>
              </div>
              <div class="associated-roots">
                Racines : {{ ticket.associated_roots.join(', ') }}
              </div>
            </div>
            
            <div v-if="withTurbo && ticket.third_position" class="ticket-turbo">
              <div class="turbo-label">Turbo (3e position)</div>
              <div class="turbo-numbers">
                <span v-for="num in ticket.third_position" :key="num" class="number-ball turbo">
                  {{ num }}
                </span>
              </div>
              <div class="combinations-info">
                {{ ticket.associated.length }}×{{ ticket.third_position.length }} = {{ ticket.associated.length * ticket.third_position.length }} combinaisons
              </div>
            </div>
          </div>
        </el-card>
      </div>
    </div>

    <div v-if="!loading && !analysis && !err" class="empty-state">
      <el-empty description="Sélectionnez un jeu et cliquez sur Analyser pour générer les champs réduits" />
    </div>

    <div v-if="loading" class="loading-state">
      <el-skeleton :rows="8" animated />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import api from '../api'

const games = ref<any[]>([])
const gamesForDate = ref<any[]>([])
const drawType = ref('')
const targetDate = ref('')
const maxDraws = ref(10) // Default to 10 draws (1 day)
const withTurbo = ref(false)
const loading = ref(false)
const analysis = ref<any>(null)
const tickets = ref<any[]>([])
const err = ref('')

// Manual mode state
const activeTab = ref('auto')
const manualDate = ref('')
const manualDrawType = ref('')
const manualGamesForDate = ref<any[]>([])
const manualData = ref<any>(null)
const manualLoading = ref(false)
const selectedBaseRoot = ref<number | null>(null)
const selectedAssociatedRoot = ref<number | null>(null)
const selectedBaseNumber = ref<number | null>(null)
const selectedAssociatedNumbers = ref<number[]>([])
const manualFieldsList = ref<any[]>([])
const dailyRootsData = ref<any>(null)
const dailyRootsLoading = ref(false)

async function load() {
  err.value = ''
  try {
    const res = await api.get('/api/lab/draw-types')
    games.value = res.data.data || []
  } catch (e: any) {
    err.value = e.response?.data?.error || e.message || 'erreur réseau'
  }
}

async function loadGamesForDate() {
  err.value = ''
  gamesForDate.value = []
  drawType.value = ''
  analysis.value = null
  tickets.value = []
  
  if (!targetDate.value) return
  
  try {
    const res = await api.get('/api/lab/draws-by-date', { params: { date: targetDate.value } })
    gamesForDate.value = res.data.data || []
  } catch (e: any) {
    err.value = e.response?.data?.error || e.message || 'erreur réseau'
  }
}

async function loadAnalysis() {
  if (!drawType.value) return
  
  loading.value = true
  err.value = ''
  analysis.value = null
  tickets.value = []
  
  try {
    const params: any = {
      draw_type: drawType.value,
      max_draws: maxDraws.value,
    }
    if (withTurbo.value) {
      params.with_turbo = 'true'
    }
    
    const res = await api.get('/api/reduced-field', { params })
    analysis.value = res.data
    tickets.value = res.data.tickets || []
  } catch (e: any) {
    err.value = e.response?.data?.error || e.message || 'erreur réseau'
  } finally {
    loading.value = false
  }
}

// Manual mode functions
async function loadManualGamesForDate() {
  manualGamesForDate.value = []
  manualDrawType.value = ''
  manualData.value = null
  dailyRootsData.value = null
  
  if (!manualDate.value) return
  
  try {
    const res = await api.get('/api/lab/draws-by-date', { params: { date: manualDate.value } })
    manualGamesForDate.value = res.data.data || []
  } catch (e: any) {
    err.value = e.response?.data?.error || e.message || 'erreur réseau'
  }
  
  dailyRootsLoading.value = true
  try {
    const res = await api.get('/api/digital-root-turbo/daily', { params: { date: manualDate.value } })
    dailyRootsData.value = res.data
  } catch (e: any) {
    err.value = e.response?.data?.error || e.message || 'erreur réseau'
  } finally {
    dailyRootsLoading.value = false
  }
}

async function loadManualData() {
  if (!manualDate.value || !manualDrawType.value) return
  
  manualLoading.value = true
  err.value = ''
  manualData.value = null
  selectedBaseRoot.value = null
  selectedAssociatedRoot.value = null
  selectedBaseNumber.value = null
  selectedAssociatedNumbers.value = []
  manualFieldsList.value = []
  
  try {
    const res = await api.get('/api/daily-played-numbers', {
      params: { date: manualDate.value, draw_type: manualDrawType.value }
    })
    manualData.value = res.data
  } catch (e: any) {
    err.value = e.response?.data?.error || e.message || 'erreur réseau'
  } finally {
    manualLoading.value = false
  }
}

const ROOT_FAMILIES = {
  0: [9, 18, 27, 36, 45, 54, 63, 72, 81, 90],
  1: [1, 10, 19, 28, 37, 46, 55, 64, 73, 82],
  2: [2, 11, 20, 29, 38, 47, 56, 65, 74, 83],
  3: [3, 12, 21, 30, 39, 48, 57, 66, 75, 84],
  4: [4, 13, 22, 31, 40, 49, 58, 67, 76, 85],
  5: [5, 14, 23, 32, 41, 50, 59, 68, 77, 86],
  6: [6, 15, 24, 33, 42, 51, 60, 69, 78, 87],
  7: [7, 16, 25, 34, 43, 52, 61, 70, 79, 88],
  8: [8, 17, 26, 35, 44, 53, 62, 71, 80, 89],
}

const allRoots = [0, 1, 2, 3, 4, 5, 6, 7, 8]

const availableRoots = computed(() => {
  if (!manualData.value) return []
  const playedRoots = Object.keys(manualData.value.played_by_root).map(Number)
  return allRoots.filter(root => !playedRoots.includes(root))
})

function getAvailableNumbers(root: number): number[] {
  if (!manualData.value || !manualData.value.played_numbers) return []
  const family = ROOT_FAMILIES[root as keyof typeof ROOT_FAMILIES] || []
  return family.filter(num => !manualData.value.played_numbers.includes(num))
}

function selectBaseNumber(num: number) {
  selectedBaseNumber.value = num
}

function toggleAssociatedNumber(num: number) {
  const index = selectedAssociatedNumbers.value.indexOf(num)
  if (index > -1) {
    selectedAssociatedNumbers.value.splice(index, 1)
  } else if (selectedAssociatedNumbers.value.length < 4) {
    selectedAssociatedNumbers.value.push(num)
  }
}

const canGenerateField = computed(() => {
  return selectedBaseNumber.value !== null && 
         selectedAssociatedNumbers.value.length === 4
})

function addManualField() {
  if (!selectedBaseNumber.value || selectedAssociatedNumbers.value.length !== 4) return
  
  // Create field object with selected numbers
  const field = {
    base: selectedBaseNumber.value,
    base_root: selectedBaseRoot.value,
    associated: [...selectedAssociatedNumbers.value],
    associated_roots: selectedAssociatedNumbers.value.map(num => {
      // Calculate digital root
      let sum = 0
      let n = num
      while (n > 0) {
        sum += n % 10
        n = Math.floor(n / 10)
      }
      while (sum >= 10) {
        sum = Math.floor(sum / 10) + (sum % 10)
      }
      return sum === 0 ? 9 : sum
    })
  }
  
  manualFieldsList.value.push(field)
  
  // Reset selections for next field
  selectedBaseRoot.value = null
  selectedAssociatedRoot.value = null
  selectedBaseNumber.value = null
  selectedAssociatedNumbers.value = []
}

function removeManualField(index: number) {
  manualFieldsList.value.splice(index, 1)
}

function clearManualFields() {
  manualFieldsList.value = []
}

onMounted(async () => {
  await load()
})
</script>

<style scoped>
.reduced-field-page {
  padding: 24px;
}
.page-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 20px;
}
.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 600;
}
.page-subtitle {
  color: var(--muted);
  font-size: 13px;
}
.error-banner {
  margin-bottom: 16px;
}
.filters-bar {
  display: flex;
  gap: 12px;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
}
.analysis-section {
  margin-bottom: 24px;
}
.analysis-card {
  border-radius: 8px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.analysis-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 20px;
}
.analysis-item h4 {
  margin: 0 0 12px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--muted);
}
.frequency-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.freq-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.freq-number {
  font-weight: 600;
  min-width: 30px;
}
.freq-count {
  font-size: 12px;
  color: var(--muted);
}
.parity-stats {
  display: flex;
  gap: 16px;
}
.parity-item {
  flex: 1;
  text-align: center;
  padding: 12px;
  border-radius: 8px;
  background: var(--bg-alt);
}
.parity-item.even {
  border-left: 4px solid #67c23a;
}
.parity-item.odd {
  border-left: 4px solid #f56c6c;
}
.parity-label {
  display: block;
  font-size: 12px;
  color: var(--muted);
}
.parity-count {
  font-size: 24px;
  font-weight: 600;
}
.root-list {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
}
.root-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  background: var(--bg-alt);
  border-radius: 6px;
}
.root-badge {
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: var(--gold);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 12px;
}
.root-count {
  font-size: 12px;
  font-weight: 600;
}
.tickets-section {
  margin-top: 24px;
}
.tickets-section h3 {
  margin: 0 0 16px 0;
  font-size: 18px;
  font-weight: 600;
}
.tickets-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
  gap: 16px;
}
.ticket-card {
  border-radius: 8px;
}
.ticket-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.ticket-strategy {
  font-weight: 600;
  font-size: 14px;
}
.ticket-content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.ticket-base {
  text-align: center;
  padding: 12px;
  background: var(--bg-alt);
  border-radius: 8px;
  border-left: 4px solid #409eff;
}
.base-label {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.base-number {
  font-size: 32px;
  font-weight: 700;
  color: #409eff;
}
.base-root {
  font-size: 12px;
  color: var(--muted);
  margin-top: 4px;
}
.ticket-associated {
  text-align: center;
}
.associated-label {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 8px;
}
.associated-numbers {
  display: flex;
  gap: 8px;
  justify-content: center;
  margin-bottom: 8px;
}
.number-ball {
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: var(--gold);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 14px;
}
.number-ball.turbo {
  background: #67c23a;
}
.associated-roots {
  font-size: 12px;
  color: var(--muted);
}
.ticket-turbo {
  padding-top: 12px;
  border-top: 1px solid var(--border);
  text-align: center;
}
.turbo-label {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 8px;
}
.turbo-numbers {
  display: flex;
  gap: 8px;
  justify-content: center;
  margin-bottom: 8px;
}
.combinations-info {
  font-size: 12px;
  color: var(--muted);
  font-weight: 600;
}
.empty-state {
  padding: 40px 0;
  text-align: center;
}
.loading-state {
  padding: 20px;
}

/* Manual mode styles */
.mode-tabs {
  margin-bottom: 20px;
}
.manual-section {
  margin-top: 24px;
}
.manual-card {
  border-radius: 8px;
  margin-bottom: 20px;
}
.manual-content {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 24px;
}
.played-numbers-section h4,
.field-builder h4 {
  margin: 0 0 16px 0;
  font-size: 16px;
  font-weight: 600;
}
.played-numbers-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.root-group {
  background: var(--bg-alt);
  border-radius: 8px;
  padding: 12px;
}
.root-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.root-count {
  font-size: 12px;
  color: var(--muted);
}
.played-numbers {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.played-number {
  padding: 4px 8px;
  background: #f56c6c;
  color: white;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}
.played-number.played-3h-23h {
  background: #e6a23c;
  border: 2px solid #d48806;
}
.time-window-info {
  margin-top: 12px;
  padding: 8px;
  background: var(--bg-alt);
  border-radius: 6px;
  display: flex;
  align-items: center;
  gap: 12px;
}
.time-window-count {
  font-size: 12px;
  color: var(--muted);
}

/* Daily roots section */
.daily-roots-section {
  margin-bottom: 24px;
}
.daily-roots-section h4 {
  margin-bottom: 10px;
}
.draws-table tr.current-game td {
  background: rgba(64, 158, 255, 0.12);
  font-weight: 600;
}

/* Draws table styles */
.draws-table {
  margin-bottom: 20px;
  overflow-x: auto;
}
.draws-table table {
  width: 100%;
  border-collapse: collapse;
}
.draws-table th,
.draws-table td {
  padding: 8px 12px;
  text-align: left;
  border-bottom: 1px solid var(--border);
}
.draws-table th {
  background: var(--bg-alt);
  font-weight: 600;
  font-size: 12px;
  color: var(--muted);
}
.draws-table td {
  font-size: 13px;
}

/* Root ball styles */
.num-ball.root {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  color: white;
  font-weight: 700;
  font-size: 12px;
  margin: 2px;
  box-shadow: 0 2px 4px rgba(0,0,0,0.2);
}
.field-builder {
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.field-step {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.field-step label {
  font-size: 14px;
  font-weight: 600;
  color: var(--muted);
}
.root-preview {
  margin-top: 8px;
}
.available-numbers {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 8px;
}
.available-numbers.clickable {
  cursor: pointer;
}
.available-number {
  padding: 4px 8px;
  background: #67c23a;
  color: white;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}
.available-number.clickable {
  cursor: pointer;
  transition: all 0.2s;
}
.available-number.clickable:hover {
  transform: scale(1.1);
  box-shadow: 0 2px 8px rgba(0,0,0,0.2);
}
.available-number.clickable.selected {
  background: #409eff;
  border: 2px solid #1a6fd4;
  transform: scale(1.15);
}
.available-number.played {
  background: #dcdfe6;
  color: #909399;
  cursor: not-allowed;
  opacity: 0.6;
}
.available-number.played:hover {
  transform: none;
  box-shadow: none;
}
.available-number.played-3h-23h {
  background: #e6a23c;
  border: 2px solid #d48806;
}
.available-number.played-3h-23h.played {
  background: #dcdfe6;
  border: 2px solid #d48806;
  opacity: 0.8;
}
.field-preview {
  display: flex;
  gap: 24px;
  padding: 16px;
  background: var(--bg-alt);
  border-radius: 8px;
}
.field-base,
.field-associated {
  flex: 1;
}
.field-label {
  display: block;
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 4px;
}
.field-value {
  font-size: 24px;
  font-weight: 700;
  color: #409eff;
}
.associated-preview {
  display: flex;
  gap: 8px;
}
.associated-number {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--gold);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 12px;
}
.manual-field-card {
  border-radius: 8px;
}
.manual-fields-list-card {
  border-radius: 8px;
  margin-top: 20px;
}
.manual-fields-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
}
.manual-field-item {
  border-radius: 8px;
}
.field-number {
  font-weight: 600;
  font-size: 14px;
}
.manual-field-content {
  display: flex;
  gap: 32px;
  justify-content: center;
  padding: 24px;
}
.field-base-large {
  text-align: center;
  padding: 20px;
  background: var(--bg-alt);
  border-radius: 12px;
  border-left: 4px solid #409eff;
  min-width: 120px;
}
.base-label {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 8px;
}
.base-number-large {
  font-size: 48px;
  font-weight: 700;
  color: #409eff;
  margin-bottom: 4px;
}
.base-root {
  font-size: 12px;
  color: var(--muted);
}
.field-associated-large {
  text-align: center;
}
.associated-label {
  font-size: 12px;
  color: var(--muted);
  margin-bottom: 12px;
}
.associated-numbers-large {
  display: flex;
  gap: 12px;
  justify-content: center;
  margin-bottom: 8px;
}
.number-ball-large {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: var(--gold);
  color: white;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 600;
  font-size: 18px;
}
.associated-roots-large {
  font-size: 12px;
  color: var(--muted);
}

@media (max-width: 768px) {
  .played-numbers-grid {
    grid-template-columns: repeat(2, 1fr);
  }
  .field-preview {
    flex-direction: column;
  }
  .manual-field-content {
    flex-direction: column;
    align-items: center;
  }
}
</style>
