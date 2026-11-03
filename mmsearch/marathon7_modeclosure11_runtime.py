"""Lazy11/image8/target10 inputs with explicit raw/canonical tuple-mask binding."""
from pathlib import Path
from .marathon7_local12_runtime import compact_negative
from .marathon7_local import (SourceCache as BaseCache,ensure_room,restore_journal,
    commit_journal,verify_winner_resume,read)
from .compact_eight43 import opposite_pair_ranks
from .recombine import digest


def tuple_binding(terms,indices):
    if len(set(terms))!=len(terms) or any(not all(term) for term in terms):raise ValueError('source term table must be essential and unique')
    canonical=sorted(terms);lookup={term:i for i,term in enumerate(canonical)};canonical_ids=sorted(lookup[terms[i]] for i in indices);mask=sum(1<<i for i in canonical_ids)
    return dict(source_raw_tuple_sha256=digest(terms),source_canonical_tuple_sha256=digest(canonical),selected_source_tuples_in_mask_order=[list(terms[i]) for i in indices],canonical_source_indices=canonical_ids,canonical_mask_lo=mask&((1<<64)-1),canonical_mask_hi=mask>>64)


class SourceCache(BaseCache):
    def load(self,case):
        values=super().load(case);source,verified,terms,tensors,sourcehash=values
        if len(terms)!=case['source_products']:raise ValueError('source raw term count differs from essential source count')
        if opposite_pair_ranks(terms,source['dimension']**2)!=[case['source_products']]*3:raise ValueError('source opposite-pair independence required')
        expected=tuple_binding(terms,case['source_indices'])
        if any(case.get(key)!=value for key,value in expected.items()):raise ValueError('source canonical tuple/mask binding differs')
        return values


def select_plan(bundle,chunk_id=None,max_cases=0,small_control=False):
    plan=read(Path(bundle)/('small-plan.json' if small_control else 'plan.json'));cases=plan['cases']
    if not small_control:
        if chunk_id not in (None,'000') or not 0<len(cases)<=9:raise ValueError('only explicit ninecase modeclosure pilot reviewed')
        for case in cases:
            mask=case['mask_lo']|(case['mask_hi']<<64)
            if mask>>93 or mask.bit_count()!=11 or case['source_indices']!=[i for i in range(93) if mask>>i&1] or (case['source_products'],case['source_local_products'],case['target_local_products'],case['mode_rank'])!=(93,11,10,8) or max(case['shape'])!=8 or case['shape'][case['free_axis']]!=8 or any(not 0<d<=8 for d in case['shape']):raise ValueError('case outside11/image8/target10 scope')
    if type(max_cases) is not int or max_cases<0:raise ValueError('invalid selected prefix')
    if max_cases:cases=cases[:max_cases]
    return dict(cases=cases,identity='small-control' if small_control else '000',family=dict(max_vectors=511,max_extensions=765),selected_sha256=digest(cases),catalog_plan_sha256=digest(plan))
