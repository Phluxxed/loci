"""Unmeasured fixture/oracle qualification; no model invocation."""
from pathlib import Path
import json
import shutil
import subprocess
import tempfile

from benchmarks.complete_work.evaluate import write_json

root=Path(__file__).resolve().parent/'pilot'
references={
'receipt-location':{'owner_file':'src/billing/receipt.js','owner_symbol':'makeReceiptKey','outbound_file':'src/transport/invoices.js','outbound_symbol':'sendInvoice','call_chain':['checkout','submitInvoice','makeReceiptKey','sendInvoice'],'example_key':'invoice/acme/0007'},
'inventory-contract':{'files':['src/entry.js','src/input/csv.js','src/domain/stock.js','src/domain/sku.js','src/output/wire.js'],'output':{'product_code':'AB-2','units':0,'schema':2},'invalid_numeric':'invalid count','reserved_applied_before_clamp':True},
'dispatch-ambiguity':{'registered_files':['src/channels/audit.js','src/channels/mail.js'],'selected_file':'src/channels/mail.js','selected_output':'mail:hi','unknown_kind_error':'unknown kind','target_depends_on_runtime_kind':True,'legacy_reachable_from_dispatch':False},
'zero-quantity':{'changed_file':'src/quantity.js','zero_result':{'sku':'A','quantity':0,'active':False},'error_message':'invalid quantity'}}
receipts=[]
for name,answer in references.items():
    with tempfile.TemporaryDirectory(prefix='loci-r1-oracle-') as temporary:
        source=Path(temporary)/'candidate'
        shutil.copytree(root/'tasks'/name/'source',source)
        oracle=root/'tasks'/name/'oracle.mjs'
        run=lambda:subprocess.run(['node',str(oracle),str(source)],capture_output=True,text=True)
        assert run().returncode!=0,'missing answer accepted'
        (source/'answer.json').write_text(json.dumps(answer))
        old_bug_rejected=None
        if name=='zero-quantity':
            old_bug_rejected=run().returncode!=0
            assert old_bug_rejected
            target=source/'src/quantity.js'
            text=target.read_text().replace('parsed <= 0','parsed < 0').replace("value === ''", "(typeof value === 'string' && value.trim() === '')")
            target.write_text(text)
        accepted=run()
        assert accepted.returncode==0,accepted.stderr
        (source/'answer.json').write_text(json.dumps({**answer,'contradictory_guess':'wrong'}))
        assert run().returncode!=0,'extra contradictory guess accepted'
        receipts.append({'task':name,'missing_answer_rejected':True,'reference_accepted':True,'extra_claim_rejected':True,'original_bug_rejected':old_bug_rejected})
write_json(root/'oracle-qualification.json',{'status':'passed','measured':False,'tasks':receipts})
print(json.dumps(receipts))
