"""Tiny exact exterior/quotient controls only, no N5 source reads."""
import itertools
import random
import unittest
from scripts.audit_c3_quotient_wedge7 import (full_tensor_projection,project,
                                            quotient_projection,wedge)


def coefficient_tensor(terms,width):
    answer=0
    for i,j,k in itertools.product(range(width),repeat=3):
        bit=sum(((a>>i)&1)*((b>>j)&1)*((c>>k)&1) for a,b,c in terms)%2
        answer|=bit<<((i*width+j)*width+k)
    return answer


class QuotientWedgeControls(unittest.TestCase):
    def test_all_small_wedges_match_literal_exterior_expansion(self):
        triples=list(itertools.combinations(range(4),3));lookup={t:i for i,t in enumerate(triples)}
        for a,b,c in itertools.product(range(16),repeat=3):
            answer=0
            for i,j,k in itertools.product(range(4),repeat=3):
                if len({i,j,k})==3 and (a>>i)&(b>>j)&(c>>k)&1:
                    answer^=1<<lookup[tuple(sorted((i,j,k)))]
            self.assertEqual(wedge(a,b,c,4),answer)
        rng=random.Random(711034)
        for _ in range(100):
            a,b,c,d=[rng.randrange(64) for _ in range(4)]
            self.assertEqual(wedge(a^d,b,c,6),wedge(a,b,c,6)^wedge(d,b,c,6))
            self.assertEqual(wedge(a,a,c,6),0)
            self.assertEqual(wedge(a,b,c,6),wedge(c,a,b,6))

    def test_projection_is_linear_and_has_exact_declared_kernel(self):
        q=quotient_projection([3,12],5);columns=q['projection_columns']
        self.assertEqual(q['quotient_width'],3)
        self.assertEqual({v for v in range(32) if project(v,columns)==0},{0,3,12,15})
        for a,b in itertools.product(range(32),repeat=2):
            self.assertEqual(project(a^b,columns),project(a,columns)^project(b,columns))
        self.assertEqual(len({project(v,columns) for v in range(32)}),8)

    def test_whole_c3_and_fixed_cube_maps_from_all_tensor_coefficients(self):
        rng=random.Random(713314);q=quotient_projection([3],4);columns=q['projection_columns']
        for _ in range(120):
            term=tuple(rng.randrange(1,16) for _ in range(3));a,b,c=term
            members={(a,b,c),(b,c,a),(c,a,b)}
            full=coefficient_tensor(members,4)
            actual=full_tensor_projection(full,columns,3)
            expected=wedge(*(project(v,columns) for v in term),3) if len(members)==3 else 0
            self.assertEqual(actual,expected)
            symmetric=set(itertools.permutations(term))
            self.assertEqual(full_tensor_projection(coefficient_tensor(symmetric,4),columns,3),0)
        for a in range(1,16):
            self.assertEqual(full_tensor_projection(coefficient_tensor([(a,a,a)],4),columns,3),0)


if __name__=='__main__':unittest.main()
