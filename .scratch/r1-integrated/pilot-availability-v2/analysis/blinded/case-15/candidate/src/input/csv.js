export function parseStock(text) {
  const [sku, available, reserved] = text.trim().split(',');
  return { sku, available: Number(available), reserved: Number(reserved) };
}
