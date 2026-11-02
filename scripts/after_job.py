"""Start a bounded successor only after a predecessor's result is saved."""
import argparse
import os
import json
import datetime
from pathlib import Path
import time

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--result',type=Path,required=True)
p.add_argument('command',nargs=argparse.REMAINDER)
a=p.parse_args()
config=a.result.parent/'campaign.json'
deadline=float('inf')
if config.exists():
    text=json.loads(config.read_text()).get('deadline_utc')
    if text:deadline=datetime.datetime.fromisoformat(text.replace('Z','+00:00')).timestamp()
while not a.result.exists() and time.time()<deadline:time.sleep(1)
if time.time()>=deadline:raise SystemExit('campaign deadline prevents queued successor')
if config.exists():
    candidates=list(a.result.parent.rglob('FOUND.json'))+list(a.result.parent.rglob('WINNER.json'))
    for path in candidates:
        try:
            data=json.loads(path.read_text())
            if data.get('dimension')==5 and data.get('field')==2 and len(data.get('terms',[]))<=92:
                raise SystemExit('candidate present; queued successor paused for independent verification')
        except (OSError,ValueError):pass
command=a.command[1:] if a.command[:1]==['--'] else a.command
os.execvp(command[0],command)
