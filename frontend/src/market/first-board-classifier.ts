import type { components } from '../api/schema'

export type FirstBoardCatalog = components['schemas']['ClassifierCatalogRead']
export type FirstBoardClass = components['schemas']['ClassRead']
export type FirstBoardClassification = components['schemas']['ClassificationRead']
export type FirstBoardTrend = components['schemas']['Trend']
export type FirstBoardShortPath = components['schemas']['ShortPath']
export type FirstBoardPositionBand = components['schemas']['PositionBand']
export type FirstBoardEventList = components['schemas']['FirstBoardEventListRead']
export type FirstBoardHistory = components['schemas']['FirstBoardHistoryRead']
export type FirstBoardHistoryEvent = components['schemas']['FirstBoardHistoryEventRead']

export const TREND_OPTIONS: { value: FirstBoardTrend; label: string }[] = [
  { value: 'up', label: '上升趋势' },
  { value: 'down', label: '下降趋势' },
  { value: 'sideways', label: '整体方向未明确' },
  { value: 'unknown', label: '趋势未知' },
]

export const SHORT_PATH_OPTIONS: { value: FirstBoardShortPath; label: string }[] = [
  { value: 'up_continuation', label: '短期向上延续' },
  { value: 'up_pullback', label: '短期上升回调' },
  { value: 'down_continuation', label: '短期向下延续' },
  { value: 'down_rebound', label: '短期下降反弹' },
  { value: 'neutral', label: '短期中性' },
  { value: 'unknown', label: '短期路径未知' },
]

export function positionScopeLabel(scope: FirstBoardClass['position_scope']): string {
  switch (scope) {
    case 'high':
      return '仅高位'
    case 'mid_or_low':
      return '中位或低位'
    case 'low':
      return '仅低位'
    case 'mid':
      return '仅中位'
    case 'any':
      return '不限位置'
  }
}

export function positionBandLabel(band: FirstBoardPositionBand): string {
  switch (band) {
    case 'low':
      return '60日低位'
    case 'mid':
      return '60日中位'
    case 'high':
      return '60日高位'
    case 'unknown':
      return '60日位置未知'
  }
}
