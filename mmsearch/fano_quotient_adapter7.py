"""Pinned, query-free loader for exactly the two approved d11/b7 Fano inputs."""
import hashlib
import json
from pathlib import Path

from .backbone7 import matrix_rank
from .compact_coset43 import mode_slices, pair_column
from .compact_eight43 import exact_coordinates
from .compact_sat import BinaryBasis
from .fano_quotient_sat7 import build_problem

METADATA_MANIFEST = '959b97aaf3e95df8a0933143bf935bdd1cfae7c625b191c22cad7b75a75cb4d9'
CORE_MANIFEST = 'f0487990ecff816bf6f3b51605071f22e35b32c9cc5d0cdfa8b8378daeffb571'
CASE_NAMES = {2: 'c3-mixed15-p01-05-17-19', 3: 'c3-mixed15-p01-06-17-19'}
METADATA_CASE_SHA256 = {
    2: 'f22129d15d4e4d93baf49ae4de728d9a427c2e6d71ef64986b1e4578c0d4d58c',
    3: '899cafc0e0a4b86c46f0e04fbcf2d0b3c073f1db5de407235d09820518da3b9d'}


def load_pinned_case(campaign, ordinal):
    if type(ordinal) is not int or ordinal not in CASE_NAMES:
        raise ValueError('only the two approved b7 metadata cases are accepted')
    campaign = Path(campaign).resolve()
    metadata = campaign/'c3-surplus3-pair-metadata-nine-v1'
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    if sha(metadata/'manifest.json') != METADATA_MANIFEST:
        raise ValueError('metadata manifest differs')
    file = metadata/f'case-{ordinal:02d}.json'
    if sha(file) != METADATA_CASE_SHA256[ordinal]:
        raise ValueError('metadata case differs')
    item = json.loads(file.read_bytes())
    if (item['case'] != CASE_NAMES[ordinal] or item['ordinal'] != ordinal or item['axis'] != 0
            or item['shape'] != [11, 11, 11] or item['backbone_rank'] != 7 or item['image_rank'] != 11):
        raise ValueError('case is outside the approved d11/b7 scope')
    core_file = campaign/'binary-block-nine-core-prep-001'/f'case-{ordinal:02d}.json'
    sealed_manifest = core_file.parent/'manifest.json'
    if sha(sealed_manifest) != CORE_MANIFEST:
        raise ValueError('sealed original core manifest differs')
    sealed = json.loads(sealed_manifest.read_bytes())['cases'][ordinal]
    if (sealed['case'] != CASE_NAMES[ordinal] or sealed['core_file'] != core_file.name
            or sealed['core_input_sha256'] != item['input_core_sha256']
            or sha(core_file) != sealed['core_input_sha256']):
        raise ValueError('core input must match the sealed source-manifest entry')
    data = json.loads(core_file.read_bytes())
    slices, _ = mode_slices(data['core'], data['shape'], 0)
    basis = [int(v, 16) for v in item['space_basis_hex']]
    if slices != [int(v, 16) for v in item['raw_slices_hex']]:
        raise ValueError('all raw slice indices must match metadata')
    actual_points = {}
    for entry in item['rankone_points']:
        value = int(entry['matrix_hex'], 16)
        if (pair_column(entry['left'], entry['right'], 11) != value
                or exact_coordinates(value, basis) != int(entry['space_coordinates_hex'], 16)):
            raise ValueError('original rank-one witness differs')
        actual_points[value] = dict(left=entry['left'], right=entry['right'], column=value)
    # This is at most 2047 elementary rank checks, not a feasibility query.
    enumerated = set()
    for coordinates in range(1, 1 << 11):
        value = 0
        for t in range(11):
            if coordinates >> t & 1:value ^= basis[t]
        if matrix_rank(value, 11, 11) == 1:enumerated.add(value)
    if set(actual_points) != enumerated:
        raise ValueError('full rank-one backbone census differs')
    points = []
    for point in actual_points.values():
        if len(BinaryBasis([p['column'] for p in points]+[point['column']]).vectors) > len(points):
            points.append(point)  # Keep ORIGINAL points, not metadata GE vectors.
    if len(points) != 7:
        raise ValueError('original rank-one backbone basis is not rank seven')
    problem = build_problem(slices, 11, 11, points, basis)
    return dict(case=item['case'], ordinal=ordinal, core=data['core'], shape=data['shape'],
                problem=problem, backbone_points=points, space_basis=basis,
                input_core_sha256=item['input_core_sha256'], metadata_case_sha256=sha(file),
                metadata_manifest_sha256=METADATA_MANIFEST, core_manifest_sha256=CORE_MANIFEST)
