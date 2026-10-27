export function parseQuantity(value) {
  const parsed = typeof value === 'number' ? value : Number(value);
  const invalidZero = parsed === 0 && !(value === 0 || (typeof value === 'string' && value.trim() !== ''));
  if (!Number.isInteger(parsed) || parsed < 0 || invalidZero || typeof value === 'boolean' || value == null) {
    throw new Error('invalid quantity');
  }
  return parsed;
}
