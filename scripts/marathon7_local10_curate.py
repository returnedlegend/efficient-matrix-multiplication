#!/usr/bin/env python3
"""Create compact portable closure inputs and measured, deduplicated summaries."""
from datetime import datetime,timedelta
import gzip
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.prepare_local_ten43 import read,sha
from mmsearch.recombine import digest


def main():
    c=ROOT/'artifacts/marathon7_20261103T122417Z';retired=c/'local10-lowrank-family-retired-v1';r=read(retired/'RETIREMENT.json');b=c/'marathon7-local-local10-ready-v5'
    if r['status']!='RETIRED_EXACT_FIXED_FAMILY_ALL111605_NEGATIVE':raise ValueError('finite family not retired')
    target=ROOT/'research/marathon7';evidence=target/'evidence';evidence.mkdir(parents=True,exist_ok=True)
    old=ROOT/'artifacts/rl_campaign42_20261103T033116Z';groups=[('legacy_exact_pilot',[old/'local-ten43-pilot12-001'])]
    for version,pattern in [('C7_v2',r'marathon7-local-local10-\d{3}'),('C7_v3',r'marathon7-local-local10-v3-\d{3}'),('C7_v4',r'marathon7-local-local10-v4-\d{3}'),('C7_v5',r'marathon7-local-local10-v5-\d{3}')]:
        groups.append((version,sorted(p for p in c.iterdir() if p.is_dir() and re.fullmatch(pattern,p.name))))
    phases=[];unknown=[];launcher_files=set();starts=[];ends=[]
    for label,outputs in groups:
        record=dict(phase=label,output_runs=len(outputs),exact_masks_newly_closed=0,input_decoder_calls=0,unknown_attempts=0,launcher_runs=0,cpu_seconds=0.,sum_actual_launcher_wall_seconds=0.,runner_wall_seconds_for_reference_only=0.);launchpins=set()
        for output in outputs:
            summary=read(output/'summary.json');cursor=read(output/'cursor.json');launchpins.add(read(output/'config.json')['launch_manifest_sha256']);record['exact_masks_newly_closed']+=cursor['next_case'];record['input_decoder_calls']+=summary['queries_this_invocation'];record['runner_wall_seconds_for_reference_only']+=summary['elapsed_seconds']
            pending=cursor.get('pending_unknown')
            if pending:
                file=output/pending['result_file'];result=read(file);match=re.fullmatch(r's([0-3])-([0-9a-f]+)',pending['case']);assert match and result['status']=='UNKNOWN';mask=int(match.group(2),16)
                unknown.append(dict(phase=label,case=pending['case'],source_id=int(match.group(1)),mask_lo_hex=hex(mask&((1<<64)-1)),mask_hi_hex=hex(mask>>64),result_sha256=sha(file),resolved_by_later_exact_proof=True,original_artifact_preserved=True));record['unknown_attempts']+=1
            launcher=output.parent/(output.name+'-job.result.json')
            if not launcher.exists():raise ValueError('missing actual launcher timing: '+str(launcher))
            if launcher in launcher_files:raise ValueError('double-counted launcher attempt')
            launcher_files.add(launcher);value=read(launcher);record['launcher_runs']+=1;record['cpu_seconds']+=value['cpu_seconds'];record['sum_actual_launcher_wall_seconds']+=value['elapsed_seconds']
            if label!='legacy_exact_pilot':
                start=datetime.fromisoformat(value['started_utc'].replace('Z','+00:00'));starts.append(start);ends.append(start+timedelta(seconds=value['elapsed_seconds']))
        if len(launchpins)!=1:raise ValueError('phase has mixed input/runtime launch pins')
        record['launch_manifest_sha256']=next(iter(launchpins));snapshot=old/'local-ten43-ready-v3' if label=='legacy_exact_pilot' else c/('marathon7-local-local10-ready-'+label.split('_')[1])
        record['snapshot_manifest_sha256']=sha(snapshot/'manifest.json');record['snapshot_path']=str(snapshot.relative_to(ROOT));phases.append(record)
    assert sum(p['exact_masks_newly_closed'] for p in phases)==111605
    assert sum(p['input_decoder_calls'] for p in phases)==111607 and len(unknown)==2
    catalogue=Path(r['original_catalog']);source_hashes={str(s):sha(b/f'source-{s}.json') for s in range(4)}
    runtime={str(path.relative_to(b/'runtime')):sha(path) for path in sorted((b/'runtime').rglob('*.py'))}
    archive=evidence/'local10_full_closure_replay_inputs.tar.gz';payload=io.BytesIO()
    with tarfile.open(fileobj=payload,mode='w') as tar:
        files=[(f'source-{s}.json',(b/f'source-{s}.json').read_bytes()) for s in range(4)]+[('survivors.tsv.gz',catalogue.read_bytes())]
        files += [('runtime/'+str(path.relative_to(b/'runtime')),path.read_bytes()) for path in sorted((b/'runtime').rglob('*.py'))]
        meta=dict(source_sha256=source_hashes,input_catalogue_sha256=sha(catalogue),runtime_file_sha256=runtime,original_frozen_v5_manifest_sha256=sha(b/'manifest.json'),scope='Exact source and complete input metadata plus frozen runtime Python. No raw case outputs or solver state.')
        files.append(('REPLAY-INPUTS.json',(json.dumps(meta,sort_keys=True,indent=2)+'\n').encode()))
        verifier="""from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parent
meta=json.loads((root/'REPLAY-INPUTS.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
for source,expected in meta['source_sha256'].items():assert sha(root/f'source-{source}.json')==expected
assert sha(root/'survivors.tsv.gz')==meta['input_catalogue_sha256']
for name,expected in meta['runtime_file_sha256'].items():assert sha(root/'runtime'/name)==expected
print('All archived source/catalogue/runtime hashes match; no decoder called.')
"""
        files.append(('verify_inputs.py',verifier.encode()))
        for name,content in files:
            info=tarfile.TarInfo(name);info.size=len(content);info.mode=0o444;info.mtime=0;tar.addfile(info,io.BytesIO(content))
    archive.write_bytes(gzip.compress(payload.getvalue(),compresslevel=6,mtime=0))
    closure=dict(status=r['status'],field=2,dimension=5,source_products=93,local_products=10,target_products=9,free_image_rank=8,unique_source_mask_keys=111605,duplicate_exact_proof_keys=0,
        original_input_catalogue_sha256=sha(catalogue),source_sha256=source_hashes,categories=r['categories'],source_counts=r['source_counts'],
        input_decoder_calls=111607,exact_negative_keys=111605,prior_unknown_attempts=2,prior_unknown_now_resolved=2,unresolved_unknown_keys=0,unknown_attempts=unknown,
        measured=dict(launcher_attempts=len(launcher_files),cpu_seconds=sum(p['cpu_seconds'] for p in phases),sum_actual_launcher_wall_seconds=sum(p['sum_actual_launcher_wall_seconds'] for p in phases),C7_phase_elapsed_seconds_including_dispatch_and_prep_gaps=(max(ends)-min(starts)).total_seconds(),
            accounting='Each distinct timed launcher attempt counted once, including the two incomplete attempts. Nested runner times are reference only and are not added to launcher wall. Configured wall_seconds budgets are never treated as elapsed time.'),phases=phases,
        snapshots=dict(v5_manifest_sha256=sha(b/'manifest.json'),v5_launch_manifest_sha256=sha(b/'launch-manifest.json'),rank2_decoder_sha256=sha(b/'runtime/mmsearch/compact_rank2_edges43.py'),guard_sha256=sha(b/'runtime/mmsearch/marathon7_cached_guard.py'),poller_sha256=sha(b/'runtime/mmsearch/marathon7_cancel_poller.py'),runtime_file_set_sha256=digest(runtime)),
        evidence=dict(retirement_report_sha256=sha(retired/'RETIREMENT.json'),retirement_manifest_sha256=sha(retired/'manifest.json'),exact_closure_registry_sha256=r['registry_sha256'],audit_inputs_sha256=r['audit_inputs_sha256'],remaining_batch_audit_sha256=sha(c/'local10-v5-remaining90387-audit-v1/REPORT.json'),replay_archive=str(archive.relative_to(ROOT)),replay_archive_sha256=sha(archive),replay_archive_bytes=archive.stat().st_size),
        retired=True,no_further_source_expansion=True,scope='Only the recorded 111605 necessary-survivor fixed-source/mask residuals. No unrestricted/global rank lower bound, no new 92-product construction.')
    (target/'LOCAL10_FULL_CLOSURE.json').write_text(json.dumps(closure,indent=2,sort_keys=True)+'\n')
    mode=read(c/'modeclosure11-pilot9-result-audit-v1.json');prep=read(c/'modeclosure11-prep-v1/REPORT.json');mode_summary=dict(status=mode['status'],source_sha256=source_hashes,parent_count=64,raw_extensions=5312,closure_size_histogram=prep['closure_size_histogram'],new_masks=9,local_products=11,target_products=10,free_image_rank=8,source_products=93,unknowns=0,
        actual=dict(runner_seconds=mode['elapsed_seconds'],launcher_seconds=mode['launcher_seconds'],cpu_seconds=mode['cpu_seconds'],peak_rss_kib=mode['peak_rss_kib']),
        exhaustive_repeated_pair_extensions=sum(p['extensions'] or 0 for p in mode['proofs']),source_canonical_tuple_mask_binding=True,bundle_manifest_sha256=mode['bundle_manifest_sha256'],proposal_sha256=sha(c/'modeclosure11-ready-v1/PROPOSED-JOB.json'),prep_manifest_sha256=sha(c/'modeclosure11-prep-v1/manifest.json'),independent_prep_qa_sha256=sha(c/'modeclosure11-independent-prep-qa-v1.json'),result_audit_sha256=sha(c/'modeclosure11-pilot9-result-audit-v1.json'),proof_chain_sha256=mode['result_chain_sha256'],strong_n4_control_result_sha256=sha(c/'modeclosure11-n4-control-v1/case-00.attempt-000.result.json'),scope=mode['claim'])
    (target/'MODECLOSURE11_NINE_CASES.json').write_text(json.dumps(mode_summary,indent=2,sort_keys=True)+'\n')
    total=closure['measured'];doc=f'''# Complete local10 fixed-family closure

All **111,605** recorded source/mask keys are closed negative at local10 →9,
free image rank8, over F2. This exactly matches the original necessary-survivor
catalogue, without duplicate proof keys or unvisited masks:12 old pilot proofs,
10,706 earlier C7 proofs and100,887 v5 proofs.

There were111,607 input decoder calls. The two earlier UNKNOWN attempts were
preserved and later resolved by exact proofs after guard-cost fixes; neither
UNKNOWN was counted as negative. The final unresolved count is zero.

Distinct timed launcher attempts used **{total['cpu_seconds']:.3f} CPU seconds**
and **{total['sum_actual_launcher_wall_seconds']:.3f} summed launcher wall seconds**.
The C7 calendar interval, including dispatch/preparation gaps, was
{total['C7_phase_elapsed_seconds_including_dispatch_and_prep_gaps']:.3f} seconds.
Each launcher is counted once, including incomplete attempts; nested runner
times and configured wall budgets are not added again. Per-phase details and
all source/snapshot/evidence hashes are in [the curated JSON](LOCAL10_FULL_CLOSURE.json).

## Exact scope

These are fixed-outside residual decisions for the explicit catalogue from four
approved93-product sources. They do not prove a global lower bound for5×5
matrix multiplication, nor produce a92-product construction. The family is
retired; a new source or neighborhood requires the next strategy decision.

## Archived replay and resume

The [portable replay archive](evidence/local10_full_closure_replay_inputs.tar.gz)
contains the four byte-exact sources, complete111,605-row catalogue, frozen
runtime Python and a file-hash manifest. It excludes raw case-output files.
Extract it in an isolated directory and verify REPLAY-INPUTS.json hashes. Each
catalogue row supplies source ID, mask words, three image dimensions and free
axis. Rebuild its core with frozen SourceCache, then call frozen
compact_rank2_edges43.solve_core at budget9, that axis and max_vectors255.
Looping all catalogue rows reproduces the finite mathematical decision set.

Operational --resume uses the original frozen bundle, identical configuration
and hash-chained cursor; UNKNOWN never advances that cursor. The archived
campaign hard cutoff remains2026-11-03T19:24:17Z. Decoder-only mathematical
replay is separate from restarting that expired campaign.

## Separate mode-closure11 pilot

The64-parent factor-image census found55 closures of size10 and9 of size11.
The9 new11-term/image8/target10 masks were all negative, with209 complete
repeated-pair extensions, no UNKNOWN/error and no source expansion. Actual
runner time was1.155 seconds; source/canonical-mask checks and the genuine N4
surplus-two whole-source control passed. [Pilot pins and measurements](MODECLOSURE11_NINE_CASES.json)
keep this distinct model separate from the local10 closure.
'''
    for original,replacement in [('local10 →9','local 10 → 9'),('rank8','rank 8'),('catalogue, without','catalogue, without'),('catalogue, without duplicate proof keys or unvisited masks:12','catalogue, without duplicate proof keys or unvisited masks: 12'),('and100,887','and 100,887'),('There were111,607','There were 111,607'),('for5×5','for 5×5'),('approved93-product','approved 93-product'),('a92-product','a 92-product'),('complete111,605-row','complete 111,605-row'),('budget9','budget 9'),('max_vectors255','max_vectors=255'),('remains2026','remains 2026'),('The64-parent','The 64-parent'),('found55','found 55'),('size10','size 10'),('and9 of size11','and 9 of size 11'),('The9 new11-term/image8/target10','The 9 new 11-term/image-8/target-10'),('with209','with 209'),('was1.155','was 1.155')]:doc=doc.replace(original,replacement)
    doc=doc.replace('verify REPLAY-INPUTS.json hashes.','run `python3 -B verify_inputs.py` to verify all hashes without decoding.')
    (target/'LOCAL10_FULL_CLOSURE.md').write_text(doc)
    print(json.dumps(dict(status='CURATED_CLOSURE_READY',exact_keys=111605,input_calls=111607,prior_unknown_resolved=2,measured_cpu_seconds=total['cpu_seconds'],sum_launcher_wall_seconds=total['sum_actual_launcher_wall_seconds'],archive_bytes=archive.stat().st_size,closure_json_sha256=sha(target/'LOCAL10_FULL_CLOSURE.json'),mode_json_sha256=sha(target/'MODECLOSURE11_NINE_CASES.json')),sort_keys=True))


if __name__=='__main__':main()
