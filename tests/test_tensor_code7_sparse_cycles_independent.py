"""Independent symbolic cube-path enumeration and fixed-seed delta oracles."""
import itertools
import random
import unittest
from unittest.mock import patch
from mmsearch import tensor_code7_sparse_cycles as subject


def family_oracle(atoms):
    lookup={a:i for i,a in enumerate(atoms)};found=set()
    def keep(points,weight):
        if len(points)==len(set(points))==weight and all(p in lookup for p in points):
            found.add(sum(1<<lookup[p] for p in points))
    for x,y in itertools.permutations(atoms,2):
        for order in itertools.permutations(range(3)):
            a,b,c=order
            if x[a]==y[a] and x[b]==y[b]:
                z=list(x);z[c]^=y[c];keep([x,y,tuple(z)],3)
            if x[a]==y[a]:
                z=list(x);w=list(y);z[b]^=y[b];w[c]^=x[c];keep([x,y,tuple(z),tuple(w)],4)
            # Independently telescope through all six shortest cube paths.
            current=list(x);edges=[]
            for axis in order:
                following=list(current);following[axis]=y[axis]
                edge=list(current);edge[axis]^=following[axis]
                edges.append(tuple(edge));current=following
            keep([x,y,*edges],5)
    return found


class SparseCycleIndependentTests(unittest.TestCase):
    def test_complete_families_match_ordered_endpoint_cube_path_oracle(self):
        pool=list(itertools.product(range(1,4),repeat=3));rng=random.Random(71103522)
        dictionaries=[pool]+[rng.sample(pool,n) for n in (7,11,17,23)]
        total=0
        for atoms in dictionaries:
            report=subject.enumerate_cycles(atoms,2)
            self.assertTrue(report['complete'])
            actual=set(subject.validate_catalogue(report,atoms,2));expected=family_oracle(atoms)
            self.assertEqual(actual,expected)
            total+=len(actual)
        print('independent_identity_dictionaries',len(dictionaries),'total_verified_cycles',total)

    def test_every_returned_tiny_cycle_matches_literal_full_tensor_zero(self):
        atoms=list(itertools.product(range(1,4),repeat=3));report=subject.enumerate_cycles(atoms,2)
        for record in report['cycles']:
            mask=int(record['mask_hex'],16)
            for i,j,k in itertools.product(range(2),repeat=3):
                value=sum(((a>>i)&1)*((b>>j)&1)*((c>>k)&1)
                          for t,(a,b,c) in enumerate(atoms) if mask>>t&1)%2
                self.assertEqual(value,0)

    def test_scan_matches_all_fixed_seed_hamming_weight_differences(self):
        atoms=[(1,1,1),(2,2,2),(3,1,1),(2,1,3),(2,3,2),(1,1,2),(1,1,3)]
        report=subject.enumerate_cycles(atoms,2);cycles=subject.validate_catalogue(report,atoms,2)
        seeds=list(range(1<<len(atoms)));original=list(seeds);seen=[]
        scan=subject.scan_seed_deltas(seeds,cycles,on_negative=lambda row:seen.append(row) or False)
        expected=[(i,j,(seed^cycle).bit_count()-seed.bit_count()) for i,seed in enumerate(seeds)
                  for j,cycle in enumerate(cycles) if (seed^cycle).bit_count()<seed.bit_count()]
        self.assertEqual([(r['seed_index'],r['cycle_index'],r['delta']) for r in seen],expected)
        self.assertEqual(scan['evaluated'],len(seeds)*len(cycles));self.assertTrue(scan['complete'])
        self.assertEqual(seeds,original)

    def test_stop_before_column_generation_and_after_last_callback_is_unknown(self):
        atoms=[(1,1,1),(2,2,2),(3,1,1),(2,1,3),(2,3,2)]
        with patch.object(subject,'atom_column',side_effect=AssertionError('stopped prelude must not construct columns')):
            report=subject.enumerate_cycles(atoms,2,cancelled=lambda:True)
        self.assertEqual(report['status'],'UNKNOWN');self.assertFalse(report['complete'])
        stop=[False]
        def callback(_):stop[0]=True;return False
        report=subject.scan_seed_deltas([3],[7],cancelled=lambda:stop[0],on_negative=callback)
        self.assertEqual(report['status'],'UNKNOWN');self.assertFalse(report['complete'])
        self.assertEqual(report['evaluated'],1);self.assertEqual(report['negative_moves'],1)


if __name__=='__main__':unittest.main()
