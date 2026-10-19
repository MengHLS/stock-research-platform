/**
 * The route table, kept free of the router instance.
 *
 * Splitting it out matters for tests: constructing a router calls
 * `createWebHistory`, which needs a real `window.location`, so a test that only
 * wants to check "every nav entry has a route" would otherwise need a DOM.
 */
import type { RouteRecordRaw } from 'vue-router'

import AboutPage from './pages/AboutPage.vue'
import CatalogPage from './pages/CatalogPage.vue'
import LoginPage from './pages/LoginPage.vue'
import OverviewPage from './pages/OverviewPage.vue'
import PlannedPage from './pages/PlannedPage.vue'

/** A planned route: resolves, but its page states the capability is not built. */
function planned(path: string, title: string, pending: string): RouteRecordRaw {
  return { path, component: PlannedPage, meta: { title, pending } }
}

export const routes: RouteRecordRaw[] = [
  {
    path: '/login',
    name: 'login',
    component: LoginPage,
    meta: { title: '登录', public: true },
  },
  {
    // Public on purpose: a prospective user must be able to read what the
    // platform does before asking for an invitation code. It shows only the
    // real health/source state, so nothing private is exposed.
    path: '/about',
    name: 'about',
    component: AboutPage,
    meta: { title: '平台说明', public: true },
  },
  {
    // Temporary landing page while the market review overview is the primary
    // workflow. Keep this as a redirect so restoring the engineering overview
    // later only requires changing the destination.
    path: '/',
    name: 'home',
    redirect: '/market/overview',
    meta: { title: '行情复盘总览', subtitle: '日期、情绪、指数与连板结构' },
  },

  // 市场环境
  {
    path: '/market/overview',
    name: 'market-overview',
    component: () => import('./pages/MarketOverviewPage.vue'),
    meta: { title: '行情复盘总览', subtitle: '日期、情绪、指数与连板结构' },
  },
  planned('/market/limit-up', '涨停复盘明细', '等待涨停复盘数据接入。'),
  planned('/market/sentiment', '情绪周期', '等待情绪指标计算模块。'),
  {
    path: '/market/intraday',
    name: 'intraday',
    component: PlannedPage,
    meta: { title: '盘中研判', pending: '行情接口已就绪，页面待实现。' },
  },

  // 模式研究
  {
    path: '/research/patterns',
    name: 'patterns',
    component: CatalogPage,
    meta: { title: '模式库', subtitle: '私人模式目录' },
  },
  planned('/research/discover', '挖掘流水线', '等待挖掘任务与候选策略模块。'),
  planned('/research/strategies', '策略管理', '等待策略与版本模块。'),
  planned('/research/screener', '选股', '等待选股与数据集模块。'),
  planned('/research/backtest', '组合回测', '等待回测与指标模块。'),
  planned('/research/compare', '回测对比', '等待回测结果模块。'),
  planned('/research/continue', '策略续跑', '等待研究与运行溯源模块。'),

  // 复盘与进化
  planned('/review/desk', '复盘工作台', '等待复盘记录与结论模块。'),
  planned('/review/journal', '决策日志', '等待私人决策记录模块。'),

  // 研究基础设施
  {
    path: '/system/data-health',
    name: 'data-health',
    component: OverviewPage,
    meta: { title: '数据域健康', subtitle: '数据源与连通状态' },
  },
  planned('/system/datasets', '数据集', '等待数据集定义、版本与构建模块。'),
  planned('/system/stock-sync', '行情同步', '等待抓取与冻结快照模块。'),
  planned('/system/experiments', '独立实验', '等待实验配置与运行模块。'),
  planned('/system/candidates', '候选策略', '等待候选策略模块。'),
  planned('/system/params', '参数搜索', '等待参数搜索模块。'),
  planned('/system/validation', '验证总览', '等待验证与稳健性模块。'),
  planned('/system/robustness', '稳健性 / OOS', '等待样本外验证模块。'),
  planned('/system/paper', '前向纸面交易', '等待纸面交易模块。'),

  { path: '/:pathMatch(.*)*', redirect: '/market/overview' },
]
