export function makeReceiptKey(invoice) {
  return `invoice/${invoice.accountId}/${String(invoice.sequence).padStart(4, '0')}`;
}
