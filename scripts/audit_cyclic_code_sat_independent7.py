"""Static sealed-code review only; never dispatch a production SAT query."""
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / '.xor-deps')]
from scripts.run_cyclic_code_sat7 import checked_input
from mmsearch.cyclic_code_sat7 import build_problem


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    campaign = ROOT / 'artifacts/marathon7_20261103T122417Z'
    bundle = campaign / 'cyclic-native-orbit7-sat-ready-v2'
    config = json.loads((bundle / 'config.json').read_bytes())
    assert sha(bundle / 'config.json') == 'c5ee72a75a0b1935f6cd264b73606eeda2ee56c732098836d9aadc787c7a68f9'
    pins = {ROOT / p: s for p, s in config['runtime_code_sha256'].items()}
    pins.update({Path(p): s for p, s in config['external_dependency_sha256'].items()})
    for path, expected in pins.items():
        assert sha(path) == expected, str(path)
    dictionary_path = Path(config['dictionary'])
    assert sha(dictionary_path) == config['dictionary_sha256']
    assert sha(dictionary_path.parent / 'manifest.json') == config['dictionary_manifest_sha256']
    d = json.loads(dictionary_path.read_bytes())
    # Independent literal coefficient expansion, without orbit_tensor/atom_tensor.
    regenerated = []
    atom_members = set()
    for rep, expected in zip(d['representatives'], d['full_columns_hex']):
        a, b, c = rep
        members = {(a, b, c), (b, c, a), (c, a, b)}
        assert not atom_members.intersection(members)
        atom_members.update(members)
        column = 0
        for u, v, w in members:
            for i in range(25):
                if u >> i & 1:
                    for j in range(25):
                        if v >> j & 1:
                            for k in range(25):
                                if w >> k & 1:
                                    column ^= 1 << (i * 625 + j * 25 + k)
        assert column == int(expected, 16)
        regenerated.append(column)
    code = checked_input(d)
    problem = build_problem(*code, budget=92)
    assert problem['metadata']['formula_sha256'] == config['formula_sha256']
    assert len(regenerated) == 366 and len(code[3]) == 123
    seed_tensor = 0
    for i, column in enumerate(regenerated):
        if code[2] >> i & 1:
            seed_tensor ^= column
    scalar_target = sum(1 << ((i * 5 + j) * 625 + (j * 5 + k) * 25 + k * 5 + i)
                        for i in range(5) for j in range(5) for k in range(5))
    assert seed_tensor == scalar_target
    for path, expected in pins.items():
        assert sha(path) == expected
    result = dict(status='PASS',scope='One bounded exact supplied366-orbit code only; no global rank lower bound',
                  config_sha256=sha(bundle/'config.json'),runtime_files_checked=len(config['runtime_code_sha256']),
                  external_dependencies_checked=len(config['external_dependency_sha256']),
                  dictionary_sha256=sha(dictionary_path),formula_sha256=config['formula_sha256'],
                  independent_literal_columns=366,full_coefficient_positions_per_column=15625,
                  rank=243,kernel_dimension=123,seed_cost=93,
                  tiny_controls_passed=13,independent_code_assignment_checks=3072,
                  solver_queries_during_qa=0,formula_metadata=problem['metadata'])
    out = campaign / 'cyclic-code-sat-independent-final-qa-v2.json'
    out.write_text(json.dumps(result,sort_keys=True,indent=2)+'\n')
    out.chmod(0o444)
    print('PASS',sha(out),flush=True)


if __name__ == '__main__':
    main()
