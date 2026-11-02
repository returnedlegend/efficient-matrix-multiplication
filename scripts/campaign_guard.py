"""Watch campaign process trees; stop workers at the global deadline or RAM cap."""
import argparse
import datetime
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def descendants(pid, table):
    found=set()
    todo=[pid]
    while todo:
        current=todo.pop()
        if current in found:continue
        found.add(current)
        todo.extend(p for p, (parent, rss) in table.items() if parent == current)
    return found


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('directory',type=Path)
    args=p.parse_args()
    config=json.loads((args.directory/'campaign.json').read_text())
    deadline=datetime.datetime.fromisoformat(config['deadline_utc'].replace('Z','+00:00')).timestamp()
    maximum=0;last=0
    while time.time()<deadline:
        listing=subprocess.run(['ps','-eo','pid=,ppid=,rss='],capture_output=True,text=True,check=True)
        table={}
        for line in listing.stdout.splitlines():
            pid,parent,rss=map(int,line.split());table[pid]=(parent,rss)
        groups=[];pids=set()
        for file in args.directory.glob('*.running.json'):
            try:
                state=json.loads(file.read_text());groups.append(state['pid']);pids|=descendants(state['pid'],table)
                if state['pid'] in table:pids.add(table[state['pid']][0])
            except (OSError,ValueError,KeyError):pass
        rss=sum(table.get(pid,(0,0))[1]*1024 for pid in pids)
        maximum=max(maximum,rss)
        if time.time()-last>=30:
            last=time.time()
            state=dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                       rss_bytes=rss,maximum_observed_rss_bytes=maximum,processes=len(pids),groups=groups,
                       measurement='ps-based summed RSS including child processes and launchers')
            tmp=args.directory/'resource_status.json.tmp';tmp.write_text(json.dumps(state,indent=2)+'\n')
            tmp.replace(args.directory/'resource_status.json')
            with (args.directory/'resources.jsonl').open('a') as log:log.write(json.dumps(state)+'\n')
        if rss>7*1024**3:
            reason='conservative 7GiB summed-RSS guard (8GiB total limit with headroom)'
            break
        time.sleep(1)
    else:
        reason='global wall-clock deadline'
    for file in args.directory.glob('*.running.json'):
        try:
            state=json.loads(file.read_text());os.killpg(state['pid'],signal.SIGTERM)
        except (OSError,ValueError,KeyError):pass
    (args.directory/'guard_stopped.json').write_text(json.dumps(dict(reason=reason,
        maximum_observed_rss_bytes=maximum,utc=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2)+'\n')


if __name__=='__main__':main()
