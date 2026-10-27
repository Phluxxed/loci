import { parseStock } from './input/csv.js';
import { normalizeStock } from './domain/stock.js';
import { wireStock } from './output/wire.js';
export function importStock(text) { return wireStock(normalizeStock(parseStock(text))); }
