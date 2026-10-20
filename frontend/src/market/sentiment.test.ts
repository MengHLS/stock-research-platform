import { describe, expect, it } from 'vitest'

import type { LadderRead, ReviewHistoryRow } from './review'
import {
  parseSentimentWindow,
  sentimentLeaders,
  sentimentSnapshot,
  sentimentTimeline,
} from './sentiment'

function row(
  date: string,
  emotion: number | null | undefined,
  maxBoard: number | null = null,
): ReviewHistoryRow {
  return {
    date,
    assessment: 'available',
    emotion_score: emotion,
    max_board: maxBoard,
  }
}

describe('sentiment window', () => {
  it('defaults to 40 days and accepts configured whole-window values', () => {
    expect(parseSentimentWindow(undefined, 120)).toBe(40)
    expect(parseSentimentWindow('60', 120)).toBe(60)
    expect(parseSentimentWindow('120', 120)).toBe(120)
  })

  it('falls back to the nearest supported window when the source is shorter', () => {
    expect(parseSentimentWindow('60', 30)).toBe(20)
    expect(parseSentimentWindow('30', 30)).toBe(30)
  })
})

describe('sentiment snapshot', () => {
  const history = [
    row('2026-10-16', 38, 6),
    row('2026-10-14', null, null),
    row('2026-10-15', 40, 5),
  ]

  it('uses known scores only for the average and keeps missing values unknown', () => {
    const snapshot = sentimentSnapshot(history, '2026-10-16')
    expect(snapshot.average).toBe(39)
    expect(snapshot.knownScores).toBe(2)
    expect(snapshot.totalRows).toBe(3)
    expect(snapshot.current?.emotion_score).toBe(38)
  })

  it('compares with the immediately preceding ordered trading day', () => {
    const snapshot = sentimentSnapshot(history, '2026-10-16')
    expect(snapshot.previous?.date).toBe('2026-10-15')
    expect(snapshot.previous?.emotion_score).toBe(40)
  })

  it('returns no average when every score is missing', () => {
    expect(sentimentSnapshot([row('2026-10-16', null)]).average).toBeNull()
  })
})

describe('sentiment timeline', () => {
  it('returns the latest days newest first without dropping missing rows', () => {
    const rows = sentimentTimeline(
      [
        row('2026-10-13', 10),
        row('2026-10-14', null),
        row('2026-10-15', 20),
        row('2026-10-16', 30),
      ],
      3,
    )
    expect(rows.map((item) => item.date)).toEqual(['2026-10-16', '2026-10-15', '2026-10-14'])
    expect(rows[2]?.emotion_score).toBeNull()
  })
})

describe('sentiment leaders', () => {
  const ladder: LadderRead = {
    connection: [
      {
        symbol: '600001',
        name: '六板',
        sector: '算力',
        limit_up_time: '09:31',
        boards: 6,
        boards_as_of_date: '2026-10-16',
      },
      {
        symbol: '600002',
        name: '三板',
        sector: '机器人',
        limit_up_time: '10:10',
        boards: 3,
        boards_as_of_date: '2026-10-16',
      },
    ],
    first: [
      {
        symbol: '600003',
        name: '首板',
        sector: '半导体',
        limit_up_time: '09:35',
        boards: 1,
        boards_as_of_date: '2026-10-16',
      },
    ],
    broken: [
      {
        symbol: '600004',
        name: '断板',
        sector: '算力',
        limit_up_time: '',
        boards: 5,
        boards_as_of_date: '2026-10-16',
        broken_kind: 'connection',
      },
    ],
    unknown: [],
  }

  it('sorts current limit-ups by board height and excludes broken rows', () => {
    expect(sentimentLeaders(ladder).map((item) => item.name)).toEqual(['六板', '三板', '首板'])
    expect(sentimentLeaders(ladder, 2).map((item) => item.name)).toEqual(['六板', '三板'])
  })
})
