/**
 * What the product actually does, stated once.
 *
 * The login screen and the public about page both describe the platform; keeping
 * the copy here means the two cannot drift into different claims. Every entry is
 * backed by code that exists in this repository, and each claim is limited to
 * what that code does *today*. Roadmap status is not written here at all: it is
 * derived from `navigation.ts`, which already carries the honest `implemented`
 * flag.
 *
 * Two rules learned the hard way while writing this file:
 *
 * 1. An interface existing is not a feature existing. The historical review page
 *    renders its reviewed APIs; the remaining market views still point to planned
 *    pages, so capability copy must name only the page that actually exists.
 * 2. A field existing is not a behaviour existing. `catalog_entry.row_version`
 *    defaults to 1 and nothing ever increments it — there is no update endpoint —
 *    so it must not be advertised as "随写入递增".
 *
 * The prototype (Open Design) shows a fake "terminal preview" with sample quotes
 * on its login screen. Sample numbers are forbidden by the design checklist, so
 * this screen shows `PlatformStatus` — the real liveness and source state.
 */
import type { IconName } from './navigation'

export interface Capability {
  /** Stable key for tests and `v-for` keys. */
  id: string
  icon: IconName
  title: string
  summary: string
  /** Concrete, checkable facts — one per line. */
  facts: readonly string[]
}

export const capabilities: readonly Capability[] = [
  {
    id: 'market',
    icon: 'trending-up',
    title: '行情与竞价',
    summary: '行情与历史复盘已接入；总览展示真实数据，缺失和降级状态会明确标注。',
    facts: [
      '腾讯与东方财富提供指数、竞价与分钟行情',
      '新浪提供 09:25 成交数据，股数为精确值',
      '历史复盘总览支持日期切换、连板梯队、题材热力与六指数',
      '情绪周期页展示评分、14 日评级、连板趋势与当日龙头梯队',
      '全球市场页汇总美股、日韩、半导体、创业板、科创50、黄金与原油',
      '盘中研判读取真实自选快照、开盘竞价与一分钟价格/成交量',
    ],
  },
  {
    id: 'catalog',
    icon: 'layers',
    title: '模式库',
    summary: '私人研究目录，按账号隔离，只能看到本账号的记录。',
    facts: ['按创建时间分页展示', '不同账号互相不可见'],
  },
  {
    id: 'identity',
    icon: 'shield',
    title: '身份与隔离',
    summary: '账号登录与会话可撤销，私人数据按账号隔离。',
    facts: [
      '密码不可逆存储',
      '登录会话可以撤销',
      '支持邀请码、开放和关闭三种注册方式，默认使用邀请码',
    ],
  },
  {
    id: 'execution',
    icon: 'flask',
    title: '研究执行',
    summary: '研究执行器尚未接入，目前只提供基础诊断。',
    facts: ['当前只提供基础诊断能力'],
  },
]

/**
 * Three numbered points the login screen shows beside the brand.
 *
 * Each one names the module that backs it; none may describe a page that renders
 * `PlannedPage`.
 */
export const pitchPoints = [
  {
    title: '证据优先',
    body: '支持读取行情、竞价与日线，实际可用性以数据源状态为准。',
  },
  {
    title: '私人研究',
    body: '模式目录按账号隔离，只展示当前账号的数据。',
  },
  {
    title: '诚实边界',
    body: '未实现的页面明确标注"待开发"，不显示示例数据冒充真实能力。',
  },
] as const

/**
 * Things this release cannot do. Shown on the about page so a visitor never
 * infers a capability from the layout that the backend does not have.
 */
export const boundaries: readonly string[] = [
  '没有邮箱验证、密码重置邮件、多因素认证或 SSO',
  '没有实时行情推送，行情按需刷新',
  '盘中研判暂不提供七维评分、避雷规则、个人战绩或交易计划',
  '决策日志与复盘工作台尚未实现',
  '数据集冻结、策略版本、回测与纸面交易尚未实现',
  '日内行情不做历史保存，重启后需要重新获取',
]
