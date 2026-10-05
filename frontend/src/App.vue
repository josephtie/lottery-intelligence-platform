<template>
  <div class="layout">
    <nav class="sidebar">
      <div class="brand">🎰 LOTTERY INTELLIGENCE</div>

      <div v-for="group in groups" :key="group.id" class="nav-group">
        <button class="group-head" @click="openGroups[gid(group.id)] = !openGroups[gid(group.id)]">
          <span class="g-emoji">{{ group.emoji }}</span>
          <span class="g-title">{{ group.title }}</span>
          <span class="g-arrow">{{ openGroups[gid(group.id)] ? '▾' : '▸' }}</span>
        </button>
        <div v-show="openGroups[gid(group.id)]" class="group-items">
          <router-link v-for="item in group.items" :key="item.to" :to="item.to"
                      :class="{ 'sub-active': isActive(item.to) }">
            <span class="i-emoji">{{ item.emoji }}</span><span>{{ item.label }}</span>
          </router-link>
        </div>
      </div>

      <!-- tags actifs: rappel + clear -->
      <div class="tagbar" v-if="nTags > 0">
        <div class="tb-title">🏷 Filtres actifs ({{ nTags }})</div>
        <div class="tb-list">
          <span v-for="m in t.models" :key="'m' + m" class="tb-chip" @click="clear('models')">🧬 {{ short(m) }}</span>
          <span v-for="g in t.games" :key="'g' + g" class="tb-chip" @click="clear('games')">🎲 {{ g }}</span>
          <span v-for="b in t.bets" :key="'b' + b" class="tb-chip" @click="clear('bets')">🎯 {{ b }}</span>
          <span v-for="l in t.levels" :key="'l' + l" class="tb-chip" @click="clear('levels')">📊 {{ l }}</span>
        </div>
        <button class="tb-clear" @click="clearAll()">tout effacer</button>
      </div>
    </nav>
    <main class="main">
      <TokenGate />
      <TagsView />
      <router-view v-slot="{ Component }">
        <keep-alive :include="cachedViews">
          <component :is="Component" />
        </keep-alive>
      </router-view>
    </main>
  </div>
</template>

<script setup lang="ts">
import { reactive, computed } from 'vue'
import { useRoute } from 'vue-router'
import { tags, clearTags } from './store/tags'
import TagsView from './components/TagsView.vue'
import TokenGate from './components/TokenGate.vue'
import { useTagsViewStore } from './stores/tagsView'

const tagsViewStore = useTagsViewStore()
const cachedViews = computed(() => tagsViewStore.cachedViews)
import { useStore } from '@nanostores/vue'

useStore(tags)
const t = computed(() => tags.get())
const nTags = computed(() => {
  const x = tags.get()
  return x.models.length + x.games.length + x.bets.length + x.levels.length
})

const route = useRoute()
function isActive(to: string) { return route.path === to }

interface Item { to: string, label: string, emoji: string }
interface Group { id: string, title: string, emoji: string, items: Item[] }

const groups: Group[] = [
  { id: 'vue', title: 'Observation', emoji: '🏡', items: [
    { to: '/', label: 'Turbo Laboratory', emoji: '🧪' },
    { to: '/dashboard', label: 'Dashboard', emoji: '🏠' },
    { to: '/draws', label: 'Tirages', emoji: '🎲' },
    { to: '/quality', label: 'Qualité données', emoji: '⚠️' },
  ]},
  { id: 'preuves', title: 'Preuve prospective', emoji: '🔮', items: [
    { to: '/predictions', label: 'Prédictions', emoji: '�' },
    { to: '/prospective', label: 'Performance', emoji: '📈' },
  ]},
  { id: 'labo', title: 'Recherche', emoji: '�', items: [
    { to: '/research', label: 'Laboratoire', emoji: '🧬' },
    { to: '/findings', label: 'Findings', emoji: '🔬' },
  ]},
  { id: 'ops', title: 'Exploitation', emoji: '⚙️', items: [
    { to: '/ops', label: 'Jobs & sources', emoji: '⚙️' },
  ]},
]

const openGroups = reactive<Record<string, boolean>>({
  vue: true, preuves: true, labo: true, ops: true,
})
function gid(id: string) { return id }

function clear(kind: 'models' | 'games' | 'bets' | 'levels') { clearTags(kind) }
function clearAll() { clearTags() }
function short(m: string) { return m.replace('_v1', '').replace(/_/g, ' ') }
</script>

<style scoped>
.nav-group { margin-bottom: 2px; }
.group-head {
  width: 100%; display: flex; align-items: center; gap: 9px;
  background: transparent; border: none; color: var(--text);
  padding: 9px 14px 5px; font-size: 12px; cursor: pointer; text-transform: uppercase;
  letter-spacing: 0.6px; font-weight: 600;
}
.group-head:hover { color: var(--gold); }
.g-emoji { font-size: 13px; }
.g-title { flex: 1; text-align: left; color: var(--muted); }
.g-arrow { color: var(--muted); font-size: 10px; }
.group-items a {
  display: flex; align-items: center; gap: 9px;
  color: var(--muted); text-decoration: none;
  padding: 7px 18px 7px 26px; border-left: 3px solid transparent; font-size: 13.5px;
}
.group-items a:hover { color: var(--text); background: var(--panel-2); }
.group-items a.router-link-active {
  color: var(--gold); border-left-color: var(--gold); background: var(--panel-2);
}
.i-emoji { width: 20px; text-align: center; }

.tagbar {
  margin-top: 14px; padding: 8px 12px; border-top: 1px solid var(--border);
}
.tb-title { color: var(--gold); font-size: 11px; margin-bottom: 6px; }
.tb-list { display: flex; flex-wrap: wrap; gap: 4px; }
.tb-chip {
  background: rgba(230, 180, 85, 0.12); border: 1px solid var(--gold);
  color: var(--gold); border-radius: 10px; padding: 1px 8px; font-size: 10.5px;
  cursor: pointer; max-width: 150px; overflow: hidden; text-overflow: ellipsis;
  white-space: nowrap;
}
.tb-chip:hover { background: rgba(245, 108, 108, 0.15); border-color: var(--red); }
.tb-clear {
  background: none; border: none; color: var(--red); font-size: 10.5px;
  cursor: pointer; margin-top: 5px; padding: 0; text-decoration: underline;
}
</style>
