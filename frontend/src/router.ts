import { createRouter, createWebHashHistory } from 'vue-router'
import Dashboard from './views/Dashboard.vue'
import TurboLab from './views/TurboLab.vue'
import Draws from './views/Draws.vue'
import Predictions from './views/Predictions.vue'
import Prospective from './views/Prospective.vue'
import Research from './views/Research.vue'
import Findings from './views/Findings.vue'
import Quality from './views/Quality.vue'
import Statistics from './views/Statistics.vue'
import Ops from './views/Ops.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/', name: 'TurboLab', component: TurboLab,
      meta: { title: 'Turbo Laboratory', affix: true } },
    { path: '/dashboard', name: 'Dashboard', component: Dashboard, meta: { title: 'Dashboard' } },
    { path: '/draws', name: 'Draws', component: Draws, meta: { title: 'Tirages' } },
    { path: '/statistics', name: 'Statistics', component: Statistics, meta: { title: 'Statistiques' } },
    { path: '/predictions', name: 'Predictions', component: Predictions, meta: { title: 'Prédictions' } },
    { path: '/prospective', name: 'Prospective', component: Prospective, meta: { title: 'Prospective' } },
    { path: '/research', name: 'Research', component: Research, meta: { title: 'Laboratoire' } },
    { path: '/findings', name: 'Findings', component: Findings, meta: { title: 'Findings' } },
    { path: '/quality', name: 'Quality', component: Quality, meta: { title: 'Qualité' } },
    { path: '/ops', name: 'Ops', component: Ops, meta: { title: 'Opérations' } },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
export default router
