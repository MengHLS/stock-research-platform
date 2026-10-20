import type { components } from '../api/schema'

export type MarketStateDescription = components['schemas']['MarketStateDescriptionRead']
export type MarketStateLayer = components['schemas']['MarketStateLayerRead']

export const STATE_CLASSIFICATION_LABELS: Record<string, string> = {
  improving: '改善',
  weakening: '恶化',
  mixed: '分歧',
  strong: '偏强',
  weak: '偏弱',
  conflicted: '分歧',
  unavailable: '不可评估',
}

export function stateClassificationTone(classification: string): string {
  if (classification === 'improving' || classification === 'strong') return 'up'
  if (classification === 'weakening' || classification === 'weak') return 'down'
  if (classification === 'conflicted') return 'warn'
  return 'flat'
}

export function signedValueTone(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === '') return ''
  const number = Number(value)
  if (!Number.isFinite(number) || number === 0) return 'flat'
  return number > 0 ? 'up' : 'down'
}

export function formatLayerMetric(
  value: string | number | null | undefined,
  unit: 'pct' | 'pp',
): string {
  if (value === null || value === undefined || value === '') return '—'
  const number = Number(value)
  if (!Number.isFinite(number)) return '—'
  const signed = `${number > 0 ? '+' : ''}${number.toFixed(2)}`
  return unit === 'pct' ? `${signed}%` : `${signed} 个百分点`
}

export function layerLabel(layer: MarketStateLayer): string {
  return STATE_CLASSIFICATION_LABELS[layer.classification] ?? layer.classification
}
