/**
 * Navigation model, ported from the prototype's `NAV` literal.
 *
 * Two rules the prototype encodes and this file preserves:
 *
 * 1. An entry with `implemented: false` is a real roadmap item, not a working
 *    page. It is rendered visibly disabled instead of silently 404-ing, so the
 *    UI never claims a capability the backend does not have.
 * 2. Group titles are data, not markup, so the sidebar and the command palette
 *    read the same source and cannot drift.
 */
export interface NavItem {
  /** Route path. */
  path: string
  /** Stable id used by tests and the command palette. */
  id: string
  name: string
  icon: IconName
  /** False means "planned": shown, but not navigable. */
  implemented: boolean
}

export interface NavGroup {
  title: string
  items: NavItem[]
}

export const navGroups: NavGroup[] = [
  {
    title: '市场环境',
    items: [
      {
        path: '/market/overview',
        id: 'overview',
        name: '行情复盘总览',
        icon: 'trending-up',
        implemented: false,
      },
      {
        path: '/market/limit-up',
        id: 'limit-up',
        name: '涨停复盘明细',
        icon: 'flame',
        implemented: false,
      },
      {
        path: '/market/sentiment',
        id: 'sentiment',
        name: '情绪周期',
        icon: 'activity',
        implemented: false,
      },
      {
        path: '/market/intraday',
        id: 'intraday',
        name: '盘中研判',
        icon: 'target',
        implemented: true,
      },
    ],
  },
  {
    title: '模式研究',
    items: [
      {
        path: '/research/patterns',
        id: 'patterns',
        name: '模式库',
        icon: 'layers',
        implemented: true,
      },
      {
        path: '/research/discover',
        id: 'discover',
        name: '挖掘流水线',
        icon: 'flask',
        implemented: false,
      },
      {
        path: '/research/strategies',
        id: 'strategies',
        name: '策略管理',
        icon: 'list-checks',
        implemented: false,
      },
      {
        path: '/research/screener',
        id: 'screener',
        name: '选股',
        icon: 'filter',
        implemented: false,
      },
      {
        path: '/research/backtest',
        id: 'backtest',
        name: '组合回测',
        icon: 'bar-chart',
        implemented: false,
      },
      {
        path: '/research/compare',
        id: 'compare',
        name: '回测对比',
        icon: 'git-compare',
        implemented: false,
      },
      {
        path: '/research/continue',
        id: 'continue',
        name: '策略续跑',
        icon: 'play',
        implemented: false,
      },
    ],
  },
  {
    title: '复盘与进化',
    items: [
      {
        path: '/review/desk',
        id: 'review',
        name: '复盘工作台',
        icon: 'file-text',
        implemented: false,
      },
      {
        path: '/review/journal',
        id: 'journal',
        name: '决策日志',
        icon: 'pencil',
        implemented: false,
      },
    ],
  },
  {
    title: '研究基础设施',
    items: [
      {
        path: '/system/data-health',
        id: 'data-health',
        name: '数据域健康',
        icon: 'shield',
        implemented: true,
      },
      {
        path: '/system/datasets',
        id: 'datasets',
        name: '数据集',
        icon: 'database',
        implemented: false,
      },
      {
        path: '/system/stock-sync',
        id: 'stock-sync',
        name: '行情同步',
        icon: 'refresh',
        implemented: false,
      },
      {
        path: '/system/experiments',
        id: 'experiments',
        name: '独立实验',
        icon: 'flask',
        implemented: false,
      },
      {
        path: '/system/candidates',
        id: 'candidates',
        name: '候选策略',
        icon: 'crown',
        implemented: false,
      },
      {
        path: '/system/params',
        id: 'params',
        name: '参数搜索',
        icon: 'sliders',
        implemented: false,
      },
      {
        path: '/system/validation',
        id: 'validation',
        name: '验证总览',
        icon: 'target',
        implemented: false,
      },
      {
        path: '/system/robustness',
        id: 'robustness',
        name: '稳健性 / OOS',
        icon: 'layers',
        implemented: false,
      },
      {
        path: '/system/paper',
        id: 'paper',
        name: '前向纸面交易',
        icon: 'trending-up',
        implemented: false,
      },
    ],
  },
]

export type IconName =
  | 'trending-up'
  | 'activity'
  | 'flame'
  | 'bar-chart'
  | 'crown'
  | 'list-checks'
  | 'bell'
  | 'search'
  | 'sun'
  | 'moon'
  | 'chevron-left'
  | 'chevron-right'
  | 'chevron-down'
  | 'x'
  | 'refresh'
  | 'grid'
  | 'target'
  | 'layers'
  | 'sliders'
  | 'shield'
  | 'menu'
  | 'filter'
  | 'git-compare'
  | 'play'
  | 'pencil'
  | 'file-text'
  | 'database'
  | 'flask'
  | 'log-out'
  | 'user'
  | 'panel-left-close'
  | 'panel-left-open'
