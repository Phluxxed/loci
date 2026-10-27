import { makeReceiptKey } from './receipt.js';
import { sendInvoice } from '../transport/invoices.js';
export async function submitInvoice(invoice, provider) {
  const key = makeReceiptKey(invoice);
  return sendInvoice(provider, invoice, key);
}
