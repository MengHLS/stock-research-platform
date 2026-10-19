import type { components } from '../api/schema'
import type { IndexSeries } from './review'

export type GlobalMarketOverview = components['schemas']['GlobalMarketOverviewRead']
export type GlobalMarketItem = components['schemas']['GlobalMarketItemRead']
export type GlobalMarketGroup = GlobalMarketItem['group']
export type GlobalMarketBar = NonNullable<GlobalMarketItem['bars']>[number]

export interface GlobalGroupDefinition {
  key: GlobalMarketGroup
  label: string
  note: string
}

export interface GlobalGroupView extends GlobalGroupDefinition {
  items: GlobalMarketItem[]
}

export const GLOBAL_GROUPS: readonly GlobalGroupDefinition[] = [
  { key: 'us', label: '美股', note: '科技与蓝筹风险偏好' },
  { key: 'asia', label: '日韩 / 半导体', note: '亚太市场与芯片产业链' },
  { key: 'cn', label: '中国内地', note: '成长板块温度' },
  { key: 'commodity', label: '商品', note: '避险与通胀线索' },
]

export function groupGlobalItems(
  items: GlobalMarketItem[],
  activeGroup: GlobalMarketGroup | 'all' = 'all',
): GlobalGroupView[] {
  return GLOBAL_GROUPS.filter((group) => activeGroup === 'all' || group.key === activeGroup)
    .map((group) => ({
      ...group,
      items: items.filter((item) => item.group === group.key),
    }))
    .filter((group) => group.items.length > 0)
}

export function marketBreadth(items: GlobalMarketItem[]) {
  let advancing = 0
  let declining = 0
  let flat = 0
  let unavailable = 0
  for (const item of items) {
    const rawChange = item.quote?.change_pct
    if (item.quote === null || rawChange === null || rawChange === undefined || rawChange === '') {
      unavailable += 1
      continue
    }
    const change = Number(rawChange)
    if (!Number.isFinite(change)) {
      unavailable += 1
    } else if (change > 0) {
      advancing += 1
    } else if (change < 0) {
      declining += 1
    } else {
      flat += 1
    }
  }
  return { advancing, declining, flat, unavailable }
}

export function globalDetailBars(item: GlobalMarketItem): IndexSeries['bars'] {
  return (item.bars ?? []).map((bar, index, bars) => ({
    date: bar.date,
    open: bar.open,
    high: bar.high,
    low: bar.low,
    close: bar.close,
    change_pct: bar.change_pct ?? null,
    ma5: movingAverage(bars, index, 5),
    ma20: movingAverage(bars, index, 20),
    amount_source: null,
    volume_source: null,
  }))
}

function movingAverage(bars: GlobalMarketBar[], index: number, periods: number): string | null {
  if (index + 1 < periods) return null
  const closes = bars.slice(index - periods + 1, index + 1).map((bar) => Number(bar.close))
  if (closes.some((value) => !Number.isFinite(value))) return null
  return (closes.reduce((sum, value) => sum + value, 0) / periods).toFixed(2)
}

export function formatMarketTime(value: string | null | undefined): string {
  if (!value) return '时间未知'
  const parsed = new Date(value)
  if (Number.isNaN(parsed.getTime())) return '时间未知'
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: 'Asia/Shanghai',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(parsed)
}
