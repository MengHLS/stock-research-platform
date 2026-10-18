/**
 * Product identity: the one place a name, tagline or logo path is defined.
 *
 * The product is "磐石 / Quant Lab": an A-share research platform covering market
 * review, pattern research, strategy validation and a dataset backplane. The name
 * is deliberately not tied to one view (the prototype was called "涨停复盘终端",
 * which no longer describes a system with strategies, datasets and identity).
 *
 * 磐石 = "bedrock": the platform is the stable base that research stands on. The
 * mark is a stacked stone plinth — three courses for the brand lockup, two for the
 * navigation where it sits beside the `layers` icon and needs to stay distinct.
 */
export const brand = {
  /** Short name used in the UI and window title. */
  name: '磐石',
  /** Latin name, shown as the secondary line of the lockup. */
  latin: 'Quant Lab',
  /** Descriptive line for the login page and document metadata. */
  tagline: 'A 股量化研究工作台',
  description: '行情复盘、模式库、策略验证与数据集的 A 股研究平台',
} as const

/**
 * Logo variants, drawn on the same 24×24 / 1.8-stroke grid as the UI icons so the
 * brand mark and the navigation read as one family.
 *
 * `plinth` (three courses) is used at 28px and above; `plinth-compact` (two
 * courses) is used where the mark is small or sits next to the `layers` icon,
 * because three thin lines converge into a blur below ~20px.
 *
 * The path data lives in the icon table so there is one source of SVG geometry.
 */
export const logoVariants = ['plinth', 'plinth-compact'] as const

export type LogoVariant = (typeof logoVariants)[number]

/** Icon name for a logo variant; identical strings, stated once for clarity. */
export function logoIconName(variant: LogoVariant): string {
  return variant
}

/** Full lockup width the words need, in `ch`-free pixels, used to size the mark. */
export const brandMarkSizes = {
  /** Login card and other large placements. */
  large: 40,
  /** Navigation rail, expanded. */
  rail: 32,
  /** Navigation rail, collapsed. */
  railCompact: 30,
} as const
