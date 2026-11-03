"""Source-bound lazy local12 surplus-two runtime; earlier releases unchanged."""
from pathlib import Path
from .marathon7_local import (SourceCache,ensure_room,restore_journal,commit_journal,
    verify_winner_resume,read,compact_negative as compact_base)
from .recombine import digest


def select_plan(bundle,chunk_id=None,max_cases=0,small_control=False):
    plan=read(Path(bundle)/('small-plan.json' if small_control else 'plan.json'));cases=plan['cases']
    if not small_control:
        if chunk_id not in (None,'000') or len(cases)>25 or not cases:raise ValueError('only explicit atmost25case pilot000 reviewed')
        for case in cases:
            mask=case['mask_lo']|(case['mask_hi']<<64)
            if mask>>93 or mask.bit_count()!=12 or case['source_indices']!=[i for i in range(93) if mask>>i&1] or case['source_products']!=93 or case['source_local_products']!=12 or case['target_local_products']!=11 or case['mode_rank']!=9 or case['shape'][case['free_axis']]!=9 or max(case['shape'])!=9 or any(not 0<d<=9 for d in case['shape']):raise ValueError('case outside12/image9/target11 pilot scope')
    if type(max_cases) is not int or max_cases<0:raise ValueError('nonnegative prefix required')
    if max_cases:cases=cases[:max_cases]
    return dict(cases=cases,identity='small-control' if small_control else '000',family=dict(max_vectors=1023,max_extensions=1533),selected_sha256=digest(cases),catalog_plan_sha256=digest(plan))


def compact_negative(result):
    value=compact_base(result)
    for name in ['extension_cosets','tested_extensions']:
        rows=value.pop(name,None)
        if rows is not None:value[name+'_sha256']=digest(rows);value[name+'_count']=len(rows)
    if result.get('case')=='all_repeated_pair_extensions_negative':
        tested=result['tested_extensions'];cosets=result['extension_cosets']
        if result['extension_cursor']!=len(cosets) or len(tested)!=len(cosets) or [row['coset'] for row in tested]!=cosets or any(row['status']!='LOCAL_UNSAT' for row in tested) or len(set(cosets))!=len(cosets):raise ValueError('incomplete repeated-pair negative cannot close case')
    return value
