export function parseQuantity(value) {
  const parsed = typeof value === 'number' ? value : Number(value);
  if (!Number.isInteger(parsed) || parsed <= 0 || value === '' || typeof value === 'boolean' || value == null) {
    throw new Error('invalid quantity');
  }
  return parsed;
}
