from pathlib import Path
import json

root = Path('.scratch/r1-integrated/pilot/tasks').resolve()
common = '''Work only in the assigned workspace. Complete this assignment directly; do not delegate or spawn agents. Native file, search, shell and edit tools are available. Loci tools, when available, are optional; select them only if useful. Do not inspect sibling runs, observer folders, evaluator files, or other task copies. Do not change user/global configuration.\nWrite the requested structured result to answer.json. Do not add unrequested claims; cite exact relative source paths and symbols. Finish when the requested result and your directly relevant check are complete.\n'''
tasks = [
('receipt-location', 'location', {
'src/app.js': "import { submitInvoice } from './billing/submit.js';\nexport async function checkout(invoice, provider) { return submitInvoice(invoice, provider); }\n",
'src/billing/submit.js': "import { makeReceiptKey } from './receipt.js';\nimport { sendInvoice } from '../transport/invoices.js';\nexport async function submitInvoice(invoice, provider) {\n  const key = makeReceiptKey(invoice);\n  return sendInvoice(provider, invoice, key);\n}\n",
'src/billing/receipt.js': "export function makeReceiptKey(invoice) {\n  return `invoice/${invoice.accountId}/${String(invoice.sequence).padStart(4, '0')}`;\n}\n",
'src/transport/invoices.js': "export async function sendInvoice(provider, invoice, receiptKey) {\n  return provider.post('/invoices', invoice, { 'Idempotency-Key': receiptKey });\n}\n",
'src/transport/receipt.js': "export function makeReceiptKey(response) { return response.headers['x-receipt']; }\n",
'src/reports/receipt.js': "export function makeReceiptKey(row) { return `report:${row.id}`; }\n",
'src/billing/retry.js': "export function retryDelay(attempt) { return Math.min(1000 * 2 ** attempt, 8000); }\n",
}, '''A duplicate-invoice report mentions checkout's outbound Idempotency-Key. Locate the function that actually constructs that key, distinguish similarly named receipt helpers, and trace its route to the outbound header. Do not change source. Write answer.json with exactly these keys: owner_file, owner_symbol, outbound_file, outbound_symbol, call_chain (ordered symbols starting at checkout and ending at sendInvoice), example_key (accountId='acme', sequence=7).''',
{"owner_file":"src/billing/receipt.js","owner_symbol":"makeReceiptKey","outbound_file":"src/transport/invoices.js","outbound_symbol":"sendInvoice","call_chain":["checkout","submitInvoice","makeReceiptKey","sendInvoice"],"example_key":"invoice/acme/0007"}),
('inventory-contract', 'cross-file-contract', {
'src/entry.js': "import { parseStock } from './input/csv.js';\nimport { normalizeStock } from './domain/stock.js';\nimport { wireStock } from './output/wire.js';\nexport function importStock(text) { return wireStock(normalizeStock(parseStock(text))); }\n",
'src/input/csv.js': "export function parseStock(text) {\n  const [sku, available, reserved] = text.trim().split(',');\n  return { sku, available: Number(available), reserved: Number(reserved) };\n}\n",
'src/domain/stock.js': "import { canonicalSku } from './sku.js';\nexport function normalizeStock(row) {\n  if (![row.available, row.reserved].every(Number.isFinite)) throw new Error('invalid count');\n  return { sku: canonicalSku(row.sku), count: Math.max(0, row.available - row.reserved) };\n}\n",
'src/domain/sku.js': "export function canonicalSku(value) { return value.trim().toUpperCase(); }\n",
'src/output/wire.js': "export function wireStock(item) { return { product_code: item.sku, units: item.count, schema: 2 }; }\n",
'src/output/csv.js': "export function wireStock(item) { return `${item.sku},${item.count}`; }\n",
'src/input/json.js': "export function parseStock(value) { return JSON.parse(value); }\n",
}, '''A client consumes importStock's returned object. Trace the active input/domain/output contract, including reserved stock, SKU normalization, and negative availability. Do not change source. Write answer.json with exactly these keys: files (ordered active pipeline files beginning with entry.js, then csv.js, stock.js, sku.js, wire.js), output (the exact object for ' ab-2 ,5,8'), invalid_numeric (the exact error message for 'x,no,1'), reserved_applied_before_clamp (boolean).''',
{"files":["src/entry.js","src/input/csv.js","src/domain/stock.js","src/domain/sku.js","src/output/wire.js"],"output":{"product_code":"AB-2","units":0,"schema":2},"invalid_numeric":"invalid count","reserved_applied_before_clamp":True}),
('dispatch-ambiguity', 'ambiguous-relationships', {
'src/dispatch.js': "import { registry } from './registry.js';\nexport function dispatch(event) {\n  const handler = registry[event.kind];\n  if (!handler) throw new Error('unknown kind');\n  return handler(event.payload);\n}\n",
'src/registry.js': "import { handle as mail } from './channels/mail.js';\nimport { handle as audit } from './channels/audit.js';\nexport const registry = Object.assign(Object.create(null), { mail, audit });\n",
'src/channels/mail.js': "import { encode } from '../codec.js';\nexport function handle(value) { return `mail:${encode(value)}`; }\n",
'src/channels/audit.js': "export function handle(value) { return `audit:${JSON.stringify(value)}`; }\n",
'src/channels/legacy.js': "export function handle(value) { return `legacy:${value}`; }\n",
'src/codec.js': "export function encode(value) { return String(value).trim().toLowerCase(); }\n",
'src/preview.js': "import { handle } from './channels/legacy.js';\nexport function preview(value) { return handle(value); }\n",
}, '''dispatch obtains a same-named handler through a registry lookup. Identify which handlers are possible in this source snapshot, which handler is selected for event {kind:'mail', payload:' Hi '}, and what remains unknown if kind is supplied only at runtime. Do not claim one unconditional static call target. Do not change source. Write answer.json with exactly these keys: registered_files (sorted), selected_file, selected_output, unknown_kind_error, target_depends_on_runtime_kind (boolean), legacy_reachable_from_dispatch (boolean).''',
{"registered_files":["src/channels/audit.js","src/channels/mail.js"],"selected_file":"src/channels/mail.js","selected_output":"mail:hi","unknown_kind_error":"unknown kind","target_depends_on_runtime_kind":True,"legacy_reachable_from_dispatch":False}),
('zero-quantity', 'bounded-code-change', {
'src/api.js': "import { parseQuantity } from './quantity.js';\nimport { buildLine } from './line.js';\nexport function lineFromRequest(input) { return buildLine(input.sku, parseQuantity(input.quantity)); }\n",
'src/quantity.js': "export function parseQuantity(value) {\n  const parsed = typeof value === 'number' ? value : Number(value);\n  if (!Number.isInteger(parsed) || parsed <= 0 || value === '' || typeof value === 'boolean' || value == null) {\n    throw new Error('invalid quantity');\n  }\n  return parsed;\n}\n",
'src/line.js': "export function buildLine(sku, quantity) { return { sku: String(sku).trim(), quantity, active: quantity > 0 }; }\n",
'src/cli.js': "export function parseQuantity(value) { return parseInt(value, 10) || 1; }\n",
'src/ui.js': "export function quantityLabel(value) { return value === 0 ? 'none' : String(value); }\n",
'src/legacy.js': "export function buildLine(sku, quantity) { return { sku, quantity: quantity || 1 }; }\n",
}, '''The request API must accept an integer zero quantity as an inactive line. Fix the shared API quantity parser to accept numeric 0 and the string '0', while keeping positive integer behavior and rejecting negative values, fractions, non-finite numbers, empty or whitespace-only strings, booleans, null, undefined, and nonnumeric strings with Error('invalid quantity'). The similarly named CLI parser is a separate legacy contract; leave it unchanged. Make the smallest correct source change and run a relevant check. Write answer.json with exactly these keys: changed_file (the API parser path), zero_result (lineFromRequest({sku:' A ',quantity:'0'})), error_message (the invalid-input error text).''',
{"changed_file":"src/quantity.js","zero_result":{"sku":"A","quantity":0,"active":False},"error_message":"invalid quantity"}),
]
plan_tasks=[]
for name, kind, files, prompt, expected in tasks:
    directory=root/name
    source=directory/'source'
    source.mkdir(parents=True,exist_ok=True)
    files['package.json']='{"type":"module","private":true}\n'
    files['README.md']='Small inventory service fixture. No network or dependencies are required.\n'
    for path, content in files.items():
        target=source/path
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(content)
    (directory/'prompt.txt').write_text(common+'\n'+prompt+'\n')
    oracle="""import fs from 'node:fs';
import path from 'node:path';
import assert from 'node:assert/strict';
import { pathToFileURL } from 'node:url';
const root=process.argv[2];
const answer=JSON.parse(fs.readFileSync(path.join(root,'answer.json'),'utf8'));
assert.deepEqual(answer,EXPECTED);
const load=async file => import(pathToFileURL(path.join(root,file)).href);
""".replace('EXPECTED',json.dumps(expected))
    if name=='receipt-location':
        oracle+="const {checkout}=await load('src/app.js'); let sent; await checkout({accountId:'acme',sequence:7},{post:(...args)=>{sent=args;}}); assert.equal(sent[2]['Idempotency-Key'],answer.example_key);\n"
    elif name=='inventory-contract':
        oracle+="const {importStock}=await load('src/entry.js'); assert.deepEqual(importStock(' ab-2 ,5,8'),answer.output); assert.throws(()=>importStock('x,no,1'),{message:answer.invalid_numeric}); assert.deepEqual(importStock('z,8,2'),{product_code:'Z',units:6,schema:2});\n"
    elif name=='dispatch-ambiguity':
        oracle+="const {dispatch}=await load('src/dispatch.js'); assert.equal(dispatch({kind:'mail',payload:' Hi '}),answer.selected_output); assert.equal(dispatch({kind:'audit',payload:3}),'audit:3'); assert.throws(()=>dispatch({kind:'legacy',payload:3}),{message:answer.unknown_kind_error}); assert.throws(()=>dispatch({kind:'toString',payload:3}),{message:answer.unknown_kind_error});\n"
    else:
        oracle+="""const {lineFromRequest}=await load('src/api.js');
for(const value of [0,'0',1,'2',23]) assert.deepEqual(lineFromRequest({sku:' A ',quantity:value}),{sku:'A',quantity:Number(value),active:Number(value)>0});
for(const value of [-1,'-1',0.5,'0.5',NaN,Infinity,-Infinity,'',' ','\\t',true,false,null,undefined,'oops']) assert.throws(()=>lineFromRequest({sku:'A',quantity:value}),{message:'invalid quantity'});
const {parseQuantity}=await load('src/cli.js'); assert.equal(parseQuantity('0'),1);
"""
    oracle+="console.log(JSON.stringify({status:'passed'}));\n"
    (directory/'oracle.mjs').write_text(oracle)
    plan_tasks.append({'id':name,'source':str(source),'prompt':str(directory/'prompt.txt'),'oracle':str(directory/'oracle.mjs'),'criteria':{'kind':kind,'correctness':'exact structured answer plus independent runtime assertions','allowed_changes':['answer.json']+(['src/quantity.js'] if name=='zero-quantity' else [])}})
(root.parent/'task-plan.json').write_text(json.dumps(plan_tasks,indent=2)+'\n')
