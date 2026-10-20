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
  {
    path: '/market/limit-up',
    name: 'market-limit-up',
    component: () => import('./pages/MarketLimitUpPage.vue'),
    meta: { title: '涨跌停复盘', subtitle: '观察日、涨跌停日历、涨停与断板明细' },
  },
  {
    path: '/market/global',
    name: 'market-global',
    component: () => import('./pages/GlobalMarketsPage.vue'),
    meta: { title: '全球市场', subtitle: '跨市场指数、半导体与商品' },
  },
  {
    path: '/market/sentiment',
    name: 'market-sentiment',
    component: () => import('./pages/MarketSentimentPage.vue'),
    meta: { title: '情绪周期', subtitle: '情绪评分、连板高度与龙头梯队' },
  },
  {
    path: '/market/intraday',
    name: 'intraday',
    component: () => import('./pages/IntradayPage.vue'),
    meta: { title: '盘中研判', subtitle: '自选、实时快照、开盘竞价与分钟行情' },
  },

  // 模式研究
  {
    path: '/research/patterns',
    name: 'patterns',
    component: CatalogPage,
    meta: { title: '模式库', subtitle: '私人模式目录' },
  },
  planned('/research/discover', '挖掘流水线', '尚在开发：挖掘任务与候选策略。'),
  planned('/research/strategies', '策略管理', '尚在开发：策略与版本。'),
  planned('/research/screener', '选股', '尚在开发：选股与数据集。'),
  planned('/research/backtest', '组合回测', '尚在开发：回测与指标。'),
  planned('/research/compare', '回测对比', '尚在开发：回测结果。'),
  planned('/research/continue', '策略续跑', '尚在开发：研究与运行溯源。'),

  // 复盘与进化
  planned('/review/desk', '复盘工作台', '尚在开发：复盘记录与结论。'),
  planned('/review/journal', '决策日志', '尚在开发：私人决策记录。'),

  // 研究基础设施
  {
    path: '/system/data-health',
    name: 'data-health',
    component: OverviewPage,
    meta: { title: '数据域健康', subtitle: '数据源与连通状态' },
  },
  planned('/system/datasets', '数据集', '尚在开发：数据集定义、版本与构建。'),
  planned('/system/stock-sync', '行情同步', '尚在开发：抓取与冻结快照。'),
  planned('/system/experiments', '独立实验', '尚在开发：实验配置与运行。'),
  planned('/system/candidates', '候选策略', '尚在开发：候选策略。'),
  planned('/system/params', '参数搜索', '尚在开发：参数搜索。'),
  planned('/system/validation', '验证总览', '尚在开发：验证与稳健性。'),
  planned('/system/robustness', '稳健性 / OOS', '尚在开发：样本外验证。'),
  planned('/system/paper', '前向纸面交易', '尚在开发：纸面交易。'),

  { path: '/:pathMatch(.*)*', redirect: '/market/overview' },
]
