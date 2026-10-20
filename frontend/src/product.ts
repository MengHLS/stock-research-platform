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
    summary: '公共行情与历史复盘接口已接入；总览展示真实数据，缺失和降级状态显式标记。',
    facts: [
      '腾讯快照与分钟K线，覆盖沪深指数',
      '东方财富 09:15–09:25 竞价曲线与撮合结果',
      '新浪 09:25 成交兜底，股数为精确值',
      'Tushare 日线，需自备 token',
      '历史复盘总览支持日期切换、连板梯队、题材热力与四指数',
      '情绪周期页展示评分、14 日评级、连板趋势与当日龙头梯队',
      '全球市场页汇总美股、日韩、半导体、创业板、科创50、黄金与原油',
    ],
  },
  {
    id: 'catalog',
    icon: 'layers',
    title: '模式库',
    summary: '私人研究目录，服务端按登录用户过滤，越权 ID 与不存在 ID 同样返回 404。',
    facts: [
      '分页读取，按创建顺序返回',
      '创建时写入 row_version=1；更新接口待实现',
      '不同账号互相不可见',
    ],
  },
  {
    id: 'identity',
    icon: 'shield',
    title: '身份与隔离',
    summary: '自建账号体系：密码不可逆存储，会话可在服务端撤销。',
    facts: [
      'scrypt 密码哈希，参数随编码可升级',
      '库中只存会话令牌的 SHA-256',
      '支持 open / invite / closed 三种注册模式，默认邀请码',
      '生产环境强制 Secure Cookie，配置缺失即拒绝启动',
    ],
  },
  {
    id: 'execution',
    icon: 'flask',
    title: '研究执行',
    summary: '持久化作业、幂等提交、租约与失败恢复；研究执行器尚未接入。',
    facts: ['独立 Worker 进程领取作业', '租约到期后可恢复', '当前只注册数据库诊断任务'],
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
    body: '行情、竞价与日线的读取接口已就绪，每个结果都标注来源与降级状态。',
  },
  {
    title: '私人研究',
    body: '模式目录按账号隔离，服务端强制用户范围，不依赖前端过滤。',
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
  '没有实时行情推送，只有按请求读取与短期缓存',
  '盘中研判页面仍是占位页；竞价接口已接入但没有独立工作台',
  '决策日志与复盘工作台尚未实现（仅模式目录有账号隔离）',
  '数据集冻结、策略版本、回测与纸面交易尚未实现',
  '日内行情不落库：重启后需要重新抓取',
]
