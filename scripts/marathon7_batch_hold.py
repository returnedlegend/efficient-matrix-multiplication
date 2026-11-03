"""Scoped stop for this authorized batch only; preserve unrelated queue jobs."""
from datetime import datetime,timezone
import copy
import fcntl
from pathlib import Path
from scripts.append_campaign_jobs42 import atomic
from scripts.prepare_local_ten43 import freeze,read,sha
from scripts.phase_coordinator42_v2 import queue_value,validate_job


def hold_batch(campaign,batch,reason,trigger=None):
    campaign=Path(campaign).resolve();batch=Path(batch).resolve();ids={job['id'] for job in read(batch/'PROPOSAL.json')['jobs']}
    marker=batch/'BATCH-HOLD.json';receipt=batch/'HOLD-RECEIPT.json'
    if not marker.exists():freeze(marker,dict(reason=reason,trigger=trigger,utc=datetime.now(timezone.utc).isoformat(),scope='Only this authorized batch; UNKNOWN remains open and is never retried.'))
    if receipt.exists() and read(receipt).get('status')=='COMMITTED':return read(receipt)
    with (campaign/'queue_append.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        queue,before=queue_value(campaign/'queue.json');state=read(campaign/'queue_state.json');registered=set(state.get('jobs',{}));updated=copy.deepcopy(queue);disabled=[]
        for old,new in zip(queue['jobs'],updated['jobs']):
            if old['id'] in ids and old['id'] not in registered and old['enabled']:
                new['enabled']=False;disabled.append(old['id'])
            if old['id'] not in ids and old!=new:raise ValueError('unrelated queue job changed')
            validate_job(new)
        evidence=dict(status='INTENT',reason=reason,trigger=trigger,batch_manifest_sha256=sha(batch/'manifest.json'),batch_marker_sha256=sha(marker),queue_before_sha256=before,disabled_unstarted_ids=disabled,
            unrelated_jobs_unchanged=True,registered_batch_jobs_not_mutated=sorted(ids&registered))
        atomic(receipt,evidence)
        if disabled:atomic(campaign/'queue.json',updated)
        evidence.update(status='COMMITTED',queue_after_sha256=sha(campaign/'queue.json'));atomic(receipt,evidence)
    return evidence
