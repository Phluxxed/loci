export function buildLine(sku, quantity) { return { sku: String(sku).trim(), quantity, active: quantity > 0 }; }
