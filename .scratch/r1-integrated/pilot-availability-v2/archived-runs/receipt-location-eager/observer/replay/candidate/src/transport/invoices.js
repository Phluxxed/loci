export async function sendInvoice(provider, invoice, receiptKey) {
  return provider.post('/invoices', invoice, { 'Idempotency-Key': receiptKey });
}
