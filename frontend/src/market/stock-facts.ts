import type { components } from '../api/schema'

/** Point-in-time industry, valuation and traded volume read from the review database. */
export type ReviewStockFacts = components['schemas']['ReviewStockFactsRead']
export type ReviewStockIndustry = components['schemas']['ReviewStockIndustryRead']
export type ReviewStockValuation = components['schemas']['ReviewStockValuationRead']
export type ReviewStockTrade = components['schemas']['ReviewStockTradeRead']
