"""Run frozen full unittest discovery; safe to re-import for spawned workers."""
def main():
    import hashlib,json,os,sys,time,unittest,resource,types
    from pathlib import Path
    OUT=Path(__file__).resolve().parent;ROOT=OUT/'source'
    os.chdir(ROOT)
    os.sched_setaffinity(0,sorted(os.sched_getaffinity(0))[:3])
    resource.setrlimit(resource.RLIMIT_AS,(3072*1024**2,3072*1024**2))
    resource.setrlimit(resource.RLIMIT_CPU,(300,300))
    live=Path('/workspace/efficient-matrix-multiplication')
    sys.path[:]=[str(ROOT),str(ROOT/'.xor-deps')]+[p for p in sys.path if p and not str(p).startswith(str(live))]
    os.environ['PYTHONPATH']=os.pathsep.join([str(ROOT),str(ROOT/'.xor-deps')])
    os.environ['PYTHONDONTWRITEBYTECODE']='1'
    frozen=ROOT/'artifacts/rl_campaign42_20261103T033116Z'
    binaries=dict(ONECOSET43_BINARY=frozen/'native-onecoset43-ready-v2/native/onecoset43',DWELL42_BASELINE_BINARY=frozen/'dwell42-ready-v1/native/baseline-worker',DWELL42_BINARY=frozen/'dwell42-ready-v1/native/dwell-worker',BURST42_BASELINE_BINARY=frozen/'plus-burst42-pilot-ready-v1/native/dwell-baseline-worker',BURST42_BINARY=frozen/'plus-burst42-pilot-ready-v1/native/plus-burst-worker')
    os.environ.update({k:str(v) for k,v in binaries.items()})
    def hashes():
        return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for directory in ('mmsearch','scripts','tests','native') for p in sorted((ROOT/directory).rglob('*')) if p.is_file() and '__pycache__' not in p.parts and p.suffix not in ('.pyc','.pyo')}
    manifest=json.loads((OUT/'snapshot-manifest.json').read_text());expected={p:r['sha256'] for p,r in manifest['files'].items()}
    before=hashes();(OUT/'hashes-before.json').write_text(json.dumps(before,indent=2,sort_keys=True)+'\n')
    if before!=expected:raise RuntimeError('snapshot pre-run bytes differ from capture manifest')
    import pycryptosat,pysat
    print('Real XOR:',pycryptosat.__file__,'PySAT:',pysat.__file__,flush=True)
    print('Frozen binaries:',json.dumps({k:dict(path=str(v),sha256=hashlib.sha256(v.read_bytes()).hexdigest()) for k,v in binaries.items()},sort_keys=True),flush=True)
    # The real campaign UTC deadline has expired. Prove production guards first,
    # then isolate only the two module clock references for tiny/planted controls.
    # No source bytes, hard deadline constants, workers, or monotonic clocks change.
    from mmsearch import cyclic_code_sat7,fano_quotient_sat7,backbone7,surplus_two7,surplus_two_large7,binary_block_descent7
    from tests.test_cyclic_code_sat7 import planted_problem
    real_deadline_checks={}
    for module,problem in [(cyclic_code_sat7,planted_problem()[0]),(fano_quotient_sat7,fano_quotient_sat7.build_problem([1,2,4,8],2,2,[]))]:
        receipt=module.solve(problem,seconds=1,memory_mb=128)
        assert receipt['status']=='UNKNOWN' and receipt['reason']=='deadline' and receipt['worker_started'] is False,receipt
        real_deadline_checks[module.__name__]=receipt
    for name,guard in [('binary_block_descent7',binary_block_descent7._Guard(1,None,binary_block_descent7.DEADLINE)),('surplus_two7',surplus_two7._Guard(None,1,surplus_two7.DEADLINE)),('surplus_two_large7',surplus_two_large7._Guard(None,1,surplus_two_large7.DEADLINE))]:
        assert guard.reason()=='deadline'
        real_deadline_checks[name]=dict(reason=guard.reason(),no_solver_called=True)
    (OUT/'real-clock-deadline-controls.json').write_text(json.dumps(real_deadline_checks,indent=2,sort_keys=True)+'\n')
    test_wall_time=cyclic_code_sat7.HARD_DEADLINE-3600
    clock_modules=(cyclic_code_sat7,fano_quotient_sat7,backbone7,surplus_two7,surplus_two_large7,binary_block_descent7)
    for module in clock_modules:
        module.time=types.SimpleNamespace(time=lambda:test_wall_time,monotonic=time.monotonic,sleep=time.sleep)
    modules=[
        'test_binary_small_slot_independent7','test_binary_small_slot_runner7',
        'test_conditional_c3_independent7','test_conditional_c3_runner7','test_conditional_surplus_three7',
        'test_cyclic_code_sat7','test_cyclic_code_sat_independent7','test_cyclic_native_corpus7','test_cyclic_native_orbit7',
        'test_fano_quotient_sat7','test_fano7_independent_controls','test_fano7_independent_math','test_run_fano_two_b7_7',
        'test_native_xor3_source7','test_compact_xor3_seed7',
        'test_tensor_code7_sparse_cycles','test_tensor_code7_sparse_cycles_independent','test_tensor_code7_sparse_cycle_run',
        'test_tensor_code7_component_sat','test_tensor_code7_even_components','test_tensor_code7_even_components_run']
    print('Targeted modules:',json.dumps(modules),flush=True)
    print('Test-only wall clock:',test_wall_time,'Real UTC deadline controls passed:',len(real_deadline_checks),flush=True)
    started=time.monotonic();suite=unittest.defaultTestLoader.loadTestsFromNames(['tests.'+m for m in modules]);result=unittest.TextTestRunner(verbosity=2).run(suite)
    after=hashes();(OUT/'hashes-after.json').write_text(json.dumps(after,indent=2,sort_keys=True)+'\n')
    changes={p:dict(before=before.get(p),after=after.get(p)) for p in sorted(before.keys()|after.keys()) if before.get(p)!=after.get(p)}
    report=dict(tests_run=result.testsRun,failures=[(str(t),s) for t,s in result.failures],errors=[(str(t),s) for t,s in result.errors],skipped=[(str(t),s) for t,s in result.skipped],expected_failures=[(str(t),s) for t,s in result.expectedFailures],unexpected_successes=[str(t) for t in result.unexpectedSuccesses],successful=result.wasSuccessful() and not changes,elapsed_seconds=time.monotonic()-started,source_hash_count_before=len(before),source_hash_count_after=len(after),source_changes=changes,snapshot_manifest_sha256=hashlib.sha256((OUT/'snapshot-manifest.json').read_bytes()).hexdigest(),code_isolated_from_live_edits=True)
    report.update(test_modules=modules,scope='Post-M4 targeted unit/regression controls; tiny/planted only; no actual N5 target solver search',real_clock_deadline_controls_passed=len(real_deadline_checks),test_only_wall_clock_epoch=test_wall_time,clock_policy='Six explicitly listed module-local time proxies during tiny/planted tests only; production hard deadline constants and monotonic clocks unchanged; real expired-deadline behavior checked before proxy',clock_proxy_modules=[m.__name__ for m in clock_modules],initial_harness_attempt='Preserved in initial-harness-attempt; 111 tests, expired inherited dependency UTC guards caused 19 subtest/test failures and 4 errors; production source unchanged',cpu_affinity=sorted(os.sched_getaffinity(0)),memory_limit_mb=3072,wall_limit_seconds=300,even_components_production_status='Prepared controller; no production run')
    report['passes']=result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped)-len(result.expectedFailures)-len(result.unexpectedSuccesses)
    (OUT/'summary.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(json.dumps(report),flush=True)
    return 0 if report['successful'] else 1

if __name__=='__main__':
    raise SystemExit(main())
