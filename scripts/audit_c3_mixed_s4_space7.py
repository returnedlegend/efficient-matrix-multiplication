"""One authorized32-direction static S4 intersection audit; no optimization."""
from __future__ import annotations
import argparse
import collections
import hashlib
import json
import os
from pathlib import Path
import resource
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.dont_write_bytecode = True
from mmsearch import cyclic_tensor_code7 as c
from mmsearch.compact_sat import BinaryBasis
from mmsearch.marathon7_cached_guard import CampaignGuard, CampaignHold
from mmsearch.marathon7_cancel_poller import CancelPoller
from scripts.audit_c3_cube_space7 import (BASE_DICT, BASE_MANIFEST, DEADLINE,
                                          intersection_witnesses, seal_check, xor)
from scripts.audit_cyclic_tensor_code7 import independent_orbit_tensor, raw

CAMPAIGN = ROOT/'artifacts/marathon7_20261103T122417Z'
CAMPAIGN_SHA = 'd71f859137dd407a29751f683afa97a0cbd23a91dbda4b6581bb5c477e671219'
BASE = CAMPAIGN/'cyclic-orbit-code7-audit-002'
OUT = CAMPAIGN/'c3-mixed-s4-space-audit-001'
CAP = 32*1024**2


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def code_pins():
    names = {str(Path(__file__).resolve().relative_to(ROOT))}
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if filename:
            path = Path(filename).resolve()
            if path.suffix == '.py' and any(path.is_relative_to(ROOT/name)
                                           for name in ('mmsearch', 'scripts')):
                names.add(str(path.relative_to(ROOT)))
    return {name: sha(ROOT/name) for name in sorted(names)}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--authorize-static-s4-audit', action='store_true')
    args = parser.parse_args(argv)
    if not args.authorize_static_s4_audit:
        parser.error('explicit root-authorized static audit flag required')
    started = time.monotonic(); cpu_started = time.process_time()
    if OUT.exists() or sha(CAMPAIGN/'campaign.json') != CAMPAIGN_SHA:
        raise ValueError('new output and matching campaign required')
    os.sched_setaffinity(0, {1}); os.setpriority(os.PRIO_PROCESS, 0, 10)
    resource.setrlimit(resource.RLIMIT_AS, (1024**3, 1024**3))
    resource.setrlimit(resource.RLIMIT_FSIZE, (CAP, CAP))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    guard = CampaignGuard(30, DEADLINE, guard_state=CAMPAIGN/'operations-v3/state.json',
                          campaign_dir=CAMPAIGN)
    guard.check('pre_static_inputs')
    signal.signal(signal.SIGTERM, lambda *_: guard.stop())
    signal.signal(signal.SIGINT, lambda *_: guard.stop())
    poller = CancelPoller(guard, lambda: started+30)
    def check(name='loop'):
        if name == 'loop':
            if poller.cancelled():
                poller.force_check(name)
        else:
            poller.force_check(name)
    seal_check(BASE, BASE_DICT, BASE_MANIFEST)
    pins = code_pins(); OUT.mkdir()
    progress = {'completed_spaces': 0}
    def save(name, value):
        check('pre_publication'); payload = value if isinstance(value, bytes) else raw(value)
        if sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file())+len(payload)>CAP:
            raise RuntimeError('32MiB aggregate audit cap')
        path=OUT/name; path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        check('post_publication')
    def alarm(*_):
        raise TimeoutError('30s static audit alarm')
    signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, max(.001, 30-(time.monotonic()-started)))
    try:
        save('config.json', dict(format='c3-mixed-s4-space-audit-config-v1',
             base_dictionary_sha256=BASE_DICT, base_manifest_sha256=BASE_MANIFEST,
             campaign_sha256=CAMPAIGN_SHA, max_distinct_spaces=32,
             factor_selection='base representative order, factor axis order, first distinct S4 spans',
             memory_mib=1024, seconds=30, cpu=1, nice=10,
             runtime_code_sha256=pins, solver_calls=0, decoding_calls=0,
             candidate_optimization_calls=0, extended_dictionaries_generated=0))
        base=json.loads((BASE/'dictionary.json').read_bytes())
        if len(base['representatives'])!=275 or base['rank']!=201:
            raise ValueError('approved275-column/rank201 corpus differs')
        cubes=[term[0] for term,weight in zip(base['representatives'],base['weights'])
               if weight==1]
        if cubes != [4096,262208,16777217]:
            raise ValueError('approved old cube forms differ')
        old_factors=BinaryBasis(cubes); seen=set(); directions=[]
        for index,term in enumerate(base['representatives']):
            for axis,value in enumerate(term):
                check()
                residue=value^old_factors.expand(old_factors.coordinates(value))
                if not residue or residue in seen:
                    continue
                seen.add(residue)
                directions.append(dict(base_representative_index=index, factor_axis=axis,
                      external_factor=value, quotient_residue_hex=hex(residue),
                      factor_forms=cubes+[value]))
                if len(directions)==32:
                    break
            if len(directions)==32:
                break
        if len(directions)!=32:
            raise ValueError('fewer than32 distinct external factor directions')
        save('directions.json', directions)
        descriptors=[coords[0] for coords in c.coordinate_orbits(4)]
        if len(descriptors)!=24:
            raise AssertionError('four-dimensional C3 invariant basis needs24 orbits')
        base_columns=[int(value,16) for value in base['full_columns_hex']]
        results=[]
        for ordinal,direction in enumerate(directions):
            check('pre_space'); forms=direction['factor_forms']; columns=[]; payload=[]
            for descriptor in descriptors:
                check(); coordinates=(descriptor//16, descriptor//4%4, descriptor%4)
                term=tuple(forms[i] for i in coordinates)
                tensor=c.orbit_tensor(term,5)
                if ordinal==0 and tensor!=independent_orbit_tensor(c.orbit(term,5),25):
                    raise ValueError('independent375000-coefficient basis check differs')
                columns.append(tensor)
                payload.append(dict(coordinate_representative=coordinates,
                                    factor_representative=term, full_tensor_hex=hex(tensor)))
            check('pre_intersection')
            result=intersection_witnesses(base_columns,columns,check)
            check('post_intersection')
            if result['base_rank']!=201 or result['space_rank']!=24 or result['intersection_dimension']<3:
                raise ValueError('old rank/space rank/cube inclusion invariant differs')
            save(f'spaces/{ordinal:02d}-basis.json', payload)
            save(f'spaces/{ordinal:02d}-intersection.json', result)
            results.append(dict(ordinal=ordinal, **direction,
                 intersection_dimension=result['intersection_dimension'], union_rank=result['union_rank'],
                 space_rank=24, basis_sha256=sha(OUT/f'spaces/{ordinal:02d}-basis.json'),
                 witness_sha256=sha(OUT/f'spaces/{ordinal:02d}-intersection.json')))
            progress['completed_spaces']=len(results)
        check('pre_final_pins'); seal_check(BASE, BASE_DICT, BASE_MANIFEST)
        if any(sha(ROOT/name)!=digest for name,digest in pins.items()):
            raise ValueError('runtime source changed during static audit')
        distribution=collections.Counter(result['intersection_dimension'] for result in results)
        manifest=dict(format='c3-mixed-s4-space-audit-v1', status='SEALED_STATIC_AUDIT',
          base_dictionary_sha256=BASE_DICT, base_manifest_sha256=BASE_MANIFEST,
          directions_sha256=sha(OUT/'directions.json'), completed_spaces=len(results),
          intersection_dimension_distribution={str(d):n for d,n in sorted(distribution.items())},
          coupling_directions=[result for result in results if result['intersection_dimension']>3],
          all_results=results, independent_first_space_entries_checked=24*15625,
          runtime_code_sha256=pins, guard=guard.observation(), poller=poller.metrics(),
          elapsed_seconds=time.monotonic()-started, process_cpu_seconds=time.process_time()-cpu_started,
          scope='Only these32 factor spans. Intersection>3 indicates coupling potential only; no improvement, feasibility, global lower bound, dictionary extension or optimization.',
          solver_calls=0, decoding_calls=0, candidate_optimization_calls=0,
          extended_dictionaries_generated=0)
        save('manifest.json',manifest)
        save('checksums.json',{str(p.relative_to(OUT)):sha(p) for p in OUT.rglob('*') if p.is_file()})
        save('COMPLETE.json',dict(manifest_sha256=sha(OUT/'manifest.json'),
                                checksums_sha256=sha(OUT/'checksums.json')))
        for path in OUT.rglob('*'):
            if path.is_file():path.chmod(0o444)
        print(json.dumps({key:manifest[key] for key in ('status','completed_spaces',
          'intersection_dimension_distribution','independent_first_space_entries_checked',
          'elapsed_seconds','process_cpu_seconds')},sort_keys=True))
        return 0
    except Exception as error:
        with (OUT/'UNKNOWN.json').open('xb') as stream:
            stream.write(raw(dict(status='UNKNOWN_STATIC_AUDIT',reason=type(error).__name__+': '+str(error),
                                  progress=progress,solver_calls=0,decoding_calls=0)))
        raise
    finally:
        signal.setitimer(signal.ITIMER_REAL,0)


if __name__=='__main__':
    raise SystemExit(main())
