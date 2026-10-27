import { parseQuantity } from './quantity.js';
import { buildLine } from './line.js';
export function lineFromRequest(input) { return buildLine(input.sku, parseQuantity(input.quantity)); }
