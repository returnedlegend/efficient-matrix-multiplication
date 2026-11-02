"""Summarize saved evidence without assuming that a recorded PID remains alive."""
import datetime
import json
import sys
from pathlib import Path

p=Path('artifacts/campaign_20261102T164324Z')
def read(f):
    try:return json.loads(f.read_text())
    except (OSError,ValueError):return {}

native=[]
for f in sorted((p/'native').glob('*/phase-*/walk.stats.json')):
    d=read(f)
    if d:native.append(dict(branch=f.parts[-3],phase=f.parts[-2],**{k:d.get(k) for k in
                      ('steps','best_rank','current_rank','elapsed_seconds','archive_size')}))
sat={}
for name in sorted({f.parent.name for f in p.glob('*/manifest.json')}):
    if name != 'sat' and not name.startswith(('compact','xor','koszul','oriented')):continue
    d=read(p/name/'manifest.json')
    if d:sat[name]=dict(attempts=d.get('attempts'),counters=d.get('counters'),
                        sources=len(d.get('sources',{})),found=d.get('found'))
def is_target(f):
    d=read(f)
    return d.get('field')==2 and d.get('dimension')==5 and 0<len(d.get('terms',[]))<=92

dictionary={folder.name:dict(rank_bound=read(folder/'result.json').get('rank_bound',read(folder/'manifest.json').get('rank_bound')), status=read(folder/'result.json').get('status','NO_SAVED_RESULT'), control_status=read(folder/'control.result.json').get('status'), dictionary_size=read(folder/'manifest.json').get('dictionary_size')) for folder in p.glob('dictionary*') if folder.is_dir()}
status=dict(dictionary=dictionary, utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
            native_steps=sum(d['steps'] for d in native),
            best_exact_rank=min([93]+[d['best_rank'] for d in native]),
            native=native, sat=sat,resources=read(p/'resource_status.json'),
            validated_target_files=[str(f) for f in list(p.rglob('WINNER.json'))+list(p.rglob('FOUND.json')) if is_target(f)],
            completed_jobs=[f.name for f in p.glob('*job.result.json')],
            native_portfolio_size=len(list((p/'native').rglob('verified/*.json'))))
tmp=p/'status.json.tmp';tmp.write_text(json.dumps(status,indent=2)+'\n');tmp.replace(p/'status.json')

if '--pulse' in sys.argv:
    active=set()
    for file in p.glob('*.running.json'):
        command=read(file).get('command',[])
        if '--output-dir' in command:
            active.add(Path(command[command.index('--output-dir')+1]).name)
    print(json.dumps(dict(utc=status['utc'],native_steps=status['native_steps'],best_exact_rank=status['best_exact_rank'],
        active_sat={k:dict(attempts=v['attempts'],outcomes={x:n for x,n in v['counters'].items() if x in ('SAT','UNSAT','UNKNOWN','ERROR','koszul_rejected')}) for k,v in sat.items() if k in active},
        rss_mib=round(status['resources'].get('rss_bytes',0)/1024**2),candidates=status['validated_target_files'],
        dictionary={k:v for k,v in dictionary.items() if k in active or k=='dictionary903'})))
elif '--tiny' in sys.argv:
    print(json.dumps(dict(utc=status['utc'], native_steps=status['native_steps'], best_exact_rank=status['best_exact_rank'], branches={k:dict(attempts=v['attempts'], outcomes={x:n for x,n in v['counters'].items() if x in ('SAT','UNSAT','UNKNOWN','ERROR','koszul_rejected')}) for k,v in sat.items()}, rss_mib=round(status['resources'].get('rss_bytes',0)/1024**2), peak_rss_mib=round(status['resources'].get('maximum_observed_rss_bytes',0)/1024**2), candidates=status['validated_target_files'], dictionary=dictionary)))
else:
    print(json.dumps({k:v for k,v in status.items() if k != 'native'} if '--brief' in sys.argv else status))
