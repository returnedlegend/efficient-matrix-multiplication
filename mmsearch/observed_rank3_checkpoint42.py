"""Append-only completed-branch ledger and source-bound cursor checks."""
import json
from pathlib import Path
from .recombine import digest


def atomic_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True);temporary=path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value,sort_keys=True)+'\n');temporary.replace(path)


def load_checkpoint(directory,quotient_sha):
    directory=Path(directory);ledger=directory/'branches.jsonl';state_path=directory/'decoder-state.json'
    prefix=[];latest=None
    if ledger.exists():
        raw=ledger.read_text()
        if raw and not raw.endswith('\n'):raise AssertionError('incomplete branch ledger tail requires review')
        for line in raw.splitlines():
            event=json.loads(line);record=event['record'];state=event['cursor']
            if event['quotient_sha256']!=quotient_sha or record['branch']!=len(prefix) or state['next_branch']!=len(prefix)+1:
                raise AssertionError('branch ledger source/contiguity mismatch')
            if latest is None:chain=digest([state['input_sha256'],state['branch_catalog_sha256']])
            else:
                if any(state[key]!=latest[key] for key in ('version','input_sha256','branch_catalog_sha256')):raise AssertionError('branch ledger decoder binding changed')
                chain=latest['prefix_chain_sha256']
            if state['prefix_chain_sha256']!=digest([chain,record]):raise AssertionError('branch ledger chain corrupted')
            prefix.append(record);latest=state
    if state_path.exists():
        stored=json.loads(state_path.read_text())
        if stored['quotient_sha256']!=quotient_sha:raise AssertionError('decoder cursor source changed')
        state=stored['cursor'];count=state['next_branch']
        if count>len(prefix):raise AssertionError('cursor skipped unrecorded completed branches')
        chain=digest([state['input_sha256'],state['branch_catalog_sha256']])
        for record in prefix[:count]:chain=digest([chain,record])
        if state['prefix_chain_sha256']!=chain:raise AssertionError('decoder cursor chain corrupted')
        if latest is None:latest=state
        elif any(state[key]!=latest[key] for key in ('version','input_sha256','branch_catalog_sha256')):raise AssertionError('cursor/ledger decoder binding mismatch')
    if latest is None:return None
    return dict(latest,completed_prefix=prefix)


def append_checkpoint(directory,quotient_sha,record,cursor):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    with (directory/'branches.jsonl').open('a') as stream:
        stream.write(json.dumps(dict(quotient_sha256=quotient_sha,record=record,cursor=cursor),sort_keys=True)+'\n');stream.flush()
    atomic_json(directory/'decoder-state.json',dict(quotient_sha256=quotient_sha,cursor=cursor))


def save_checkpoint(directory,quotient_sha,cursor):
    if cursor is None:return
    summary={key:value for key,value in cursor.items() if key!='completed_prefix'}
    # The prefix must have been streamed into the ledger; an empty initial
    # cursor is also valid when interruption occurs before the first branch.
    existing=load_checkpoint(directory,quotient_sha)
    if summary['next_branch'] and (existing is None or existing['next_branch']!=summary['next_branch'] or existing['prefix_chain_sha256']!=summary['prefix_chain_sha256']):
        raise AssertionError('final cursor advances beyond durable branch events')
    atomic_json(Path(directory)/'decoder-state.json',dict(quotient_sha256=quotient_sha,cursor=summary))
