#!/usr/bin/env python3
"""Export an explicit F2 tensor certificate to Lean 4 (kernel decide by default)."""
import argparse
import json
from pathlib import Path


def export(source, dest, native=False):
    data = json.loads(Path(source).read_text())
    if data.get('dimension') != 5 or data.get('field') != 2:
        raise ValueError('only dimension=5, field=2 certificates are supported')
    terms = data['terms']
    if not terms:
        raise ValueError('empty decomposition')
    for term in terms:
        for name in ('u', 'v', 'w'):
            if len(term[name]) != 25 or any(type(x) is not int or x not in (0, 1) for x in term[name]):
                raise ValueError('all factors must contain exactly 25 binary integers')
    out = ['import Certificate', '', 'namespace ExplicitCertificate',
           'open MatrixCertificate', 'set_option maxRecDepth 1000000',
           'set_option maxHeartbeats 0', '']
    for name in ('u', 'v', 'w'):
        rows = ','.join(str(sum(x << i for i, x in enumerate(t[name]))) for t in terms)
        out += [f'def {name}Rows : Array Nat := #[{rows}]',
                f'def {name.upper()} (r : Fin {len(terms)}) (a : Index) : Bool :=',
                f'  ({name}Rows.getD r.val 0).testBit (a.1.val * 5 + a.2.val)', '']
    out += [f'def ranks : List (Fin {len(terms)}) := List.finRange {len(terms)}', '',
            'theorem raw_certificate : ∀ ai aj bi bj ci cj : Fin 5,',
            '    sum ranks (fun r => U r (ai,aj) && V r (bi,bj) && W r (ci,cj)) =',
            '      target (ai,aj) (bi,bj) (ci,cj) := by',
            '  ' + ('native_decide' if native else 'decide'), '',
            'theorem coefficient_certificate : ∀ a b c : Index,',
            '    sum ranks (fun r => U r a && V r b && W r c) = target a b c := by',
            '  rintro ⟨ai,aj⟩ ⟨bi,bj⟩ ⟨ci,cj⟩',
            '  exact raw_certificate ai aj bi bj ci cj', '',
            'theorem multiplication_correct (A B : Index → Bool) (i k : Fin 5) :',
            '    algorithm indices indices ranks U V W A B (k,i) = matmul A B i k := by',
            '  exact matrix_multiplication_correct ranks U V W coefficient_certificate A B i k', '',
            '#print axioms coefficient_certificate', '#print axioms multiplication_correct',
            'end ExplicitCertificate', '']
    Path(dest).write_text('\n'.join(out))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('certificate')
    parser.add_argument('output')
    parser.add_argument('--native', action='store_true', help='use Lean native_decide (adds trusted native evaluator axiom)')
    args = parser.parse_args()
    export(args.certificate, args.output, args.native)
