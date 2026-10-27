import { canonicalSku } from './sku.js';
export function normalizeStock(row) {
  if (![row.available, row.reserved].every(Number.isFinite)) throw new Error('invalid count');
  return { sku: canonicalSku(row.sku), count: Math.max(0, row.available - row.reserved) };
}
