import copy
import hashlib
import itertools
import json
import unittest

from mmsearch import neighborhood_novelty43 as n
from mmsearch.local_ten43 import planted_small
from mmsearch.search import encode_candidate,naive_terms


def ordered(terms):return dict(dimension=2,field=2,terms=[encode_candidate([t],2)['terms'][0]for t in terms])
POS=[(13,1,10),(1,11,12),(1,1,6),(9,9,9),(8,5,3),(3,8,5),(5,3,8),(10,12,1)]


class NeighborhoodNoveltyControls(unittest.TestCase):
    def test_heldout_evaluation_descendants_and_unknown_ancestry_never_promoted(self):
        def node(identity,raw,parents=(),purpose='search',operation='approved_root'):
            return dict(canonical_source_identity=identity*64,raw_sha256=raw*64,provenance_sha256='f'*64,
                        parents=list(parents),purpose=purpose,operation=operation)
        root=node('a','b');child=node('c','d',['root'],operation='exact_native_walk');child['parent_raw_sha256']={'root':root['raw_sha256']}
        nodes={'root':root,'child':child};approved={'root':n.digest(root)}
        self.assertEqual(n.provenance_hold('child',nodes,approved)['status'],'ELIGIBLE_BOUND_SEARCH_ANCESTRY')
        self.assertEqual(n.provenance_hold('child',nodes,approved,{'a'*64})['status'],'EXCLUDE_EVALUATION_HELDOUT_ANCESTRY')
        evaluation=copy.deepcopy(nodes);evaluation['root']['purpose']='evaluation'
        self.assertEqual(n.provenance_hold('child',evaluation,approved)['status'],'EXCLUDE_EVALUATION_HELDOUT_ANCESTRY')
        missing={'child':child}
        self.assertEqual(n.provenance_hold('child',missing,approved)['status'],'DEFER_UNKNOWN_ANCESTRY')
        wrong=copy.deepcopy(nodes);wrong['child']['parent_raw_sha256']['root']='0'*64
        self.assertEqual(n.provenance_hold('child',wrong,approved)['status'],'DEFER_UNKNOWN_ANCESTRY')
        cycle=copy.deepcopy(nodes);cycle['root']['parents']=['child'];cycle['root']['operation']='exact_bfs';cycle['root']['parent_raw_sha256']={'child':child['raw_sha256']}
        self.assertEqual(n.provenance_hold('child',cycle,approved)['status'],'DEFER_UNKNOWN_ANCESTRY')

    def test_strict_source_hash_canonical_heldout_and_corruption_holds(self):
        source=ordered(POS)
        def check(data,**kw):
            raw=json.dumps(data).encode();return n.tiny_source_hold(raw,hashlib.sha256(raw).hexdigest(),8,**kw)
        proof=check(source);self.assertEqual(proof['full_entries_checked'],64);self.assertTrue(proof['factor_span_shortcut_allowed'])
        with self.assertRaises(ValueError):check(source,heldout={proof['canonical_identity']})
        reordered=copy.deepcopy(source);reordered['terms'].reverse()
        with self.assertRaises(ValueError):check(reordered,seen={proof['canonical_identity']})
        self.assertNotEqual(check(reordered)['ordered_terms_sha256'],proof['ordered_terms_sha256'])
        for value in [True,2]:
            bad=copy.deepcopy(source);bad['terms'][0]['u'][0]=value
            with self.assertRaises(ValueError):check(bad)
        bad=copy.deepcopy(source);bad['terms'][0]['u'][0]^=1
        with self.assertRaises(ValueError):check(bad)
        with self.assertRaises(ValueError):n.tiny_source_hold(json.dumps(source).encode(),'0'*64,8)
        raw=b'{"dimension":2,"dimension":2,"field":2,"terms":[]}'
        with self.assertRaises(ValueError):n.tiny_source_hold(raw,hashlib.sha256(raw).hexdigest(),0)
        with self.assertRaises(ValueError):check(dict(source,dimension=5))

    def test_all_short_circuits_match_independent_minimal_subset_test(self):
        values=[1,1,2,3,4,5,6,7,8,9,10,11];expected=set()
        def xor(indices):
            value=0
            for i in indices:value^=values[i]
            return value
        for size in (2,3,4):
            for ids in itertools.combinations(range(len(values)),size):
                if xor(ids):continue
                if any(xor(part)==0 for k in range(1,size)for part in itertools.combinations(ids,k)):continue
                expected.add(ids)
        actual=n.minimal_circuits(values)
        self.assertEqual({tuple(x['indices'])for x in actual},expected)
        self.assertEqual({x['size']for x in actual},{2,3,4})

    def test_union_attempt_emission_caps_and_n5_disabled(self):
        source=ordered(naive_terms(2));a=n.tiny_circuit_unions(source,max_attempts=8,max_masks=2)
        self.assertLessEqual(a['attempts'],8);self.assertLessEqual(len(a['candidates']),2)
        self.assertFalse(a['union_catalog_exhausted']);self.assertEqual(a,n.tiny_circuit_unions(source,max_attempts=8,max_masks=2))
        for item in a['candidates']:
            self.assertEqual(item['mask'],sum(1<<i for i in item['indices']))
            self.assertGreaterEqual(len({w['axis']for w in item['circuit_witnesses']}),2)
        with self.assertRaises(ValueError):n.tiny_circuit_unions(dict(source,dimension=5))

    def test_mode_route_retains_smaller_images_and_exact_known_local_controls(self):
        low=n.tiny_mode_route(ordered(naive_terms(2)),list(range(8)))
        self.assertEqual((low['route'],low['mode_rank'],low['surplus']),('RETAIN_UNSUPPORTED_SURPLUS_GE2',4,3))
        zero=n.tiny_mode_route(ordered(POS),[0,1,2]);self.assertEqual(zero['route'],'ZERO_SURPLUS_EXACT')
        source,core,_=planted_small();one=n.tiny_mode_route(source,core['source_indices']);self.assertEqual(one['route'],'ONE_COSET_EXACT')
        flatten=n.tiny_mode_route(ordered(naive_terms(2)),[0,1]);self.assertEqual(flatten['route'],'EXCLUDED_BY_MODE_RANK')
        self.assertTrue(all(x['decoder_queries']==0 for x in [low,zero,one,flatten]))
        with self.assertRaises(ValueError):n.tiny_mode_route(dict(source,dimension=5),[0,1])

    def test_constructive_basis_map_and_corruption_rejection(self):
        source,core,_=planted_small();old=n.tiny_mode_route(source,core['source_indices'])
        products=[(3,5,9),(3,10,6),(12,5,6)]
        new=copy.deepcopy(old);new['image_bases']=[[1,2],[4,8],[3,12]]
        result=n.tiny_constructive_equivalence(old,new,products)
        self.assertEqual(result['status'],'CONSTRUCTIVE_MAP_VERIFIED');self.assertFalse(result['negative_transferred'])
        bad=copy.deepcopy(new);bad['image_bases'][0]=[1,1]
        with self.assertRaises(ValueError):n.tiny_constructive_equivalence(old,bad,products)
        bad=[list(t)for t in products];bad[0][0]^=1
        with self.assertRaises((AssertionError,ValueError)):n.tiny_constructive_equivalence(old,new,bad)


if __name__=='__main__':unittest.main()
