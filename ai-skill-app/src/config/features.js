/** Product feature flags (Vite env). */
export const ENABLE_LEGACY_BIDS = String(import.meta.env.VITE_ENABLE_LEGACY_BIDS || '').toLowerCase() === 'true'
