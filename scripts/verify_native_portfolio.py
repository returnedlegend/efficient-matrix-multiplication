"""Reverify each saved native candidate and export its independent verifier."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from mmsearch.search import decode_candidate
from mmsearch.verify import verify_file,write_standalone_verifier

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('campaign',type=Path)
a=p.parse_args();count=0;entries=0;ranks=Counter();unique=set();invalid=[]
out=a.campaign/'native_portfolio_verification.jsonl'
with out.open('w') as log:
    for file in sorted((a.campaign/'native').rglob('verified/*.json')):
        data=json.loads(file.read_text())
        if 'terms' not in data:continue
        report=verify_file(file,random_trials=4,seed=0)
        record=dict(path=str(file),sha256=hashlib.sha256(file.read_bytes()).hexdigest(),verification=report)
        log.write(json.dumps(record)+'\n');count+=1;entries+=report['exact_entries_checked']
        if not report['valid']:invalid.append(str(file));continue
        ranks[report['rank']]+=1
        unique.add(tuple(sorted(decode_candidate(data,data['dimension']))))
        write_standalone_verifier(file.with_suffix('.verify.py'))
summary=dict(candidates_checked=count,unique_termsets=len(unique),exact_coefficients_checked=entries,
             ranks=dict(ranks),invalid=invalid,report_sha256=hashlib.sha256(out.read_bytes()).hexdigest())
(a.campaign/'native_portfolio_verification_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary))
raise SystemExit(bool(invalid))
