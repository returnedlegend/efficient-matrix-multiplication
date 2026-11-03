"""Necessary CP bound from the span of low-matrix-rank mode-image points."""
import math
from .compact_coset43 import mode_slices
from .compact_sat import BinaryBasis
from .sat_neighborhoods import gf2_rank
from .recombine import digest


def matrix_rank(value,rows,columns):
    if type(value) is not int or value<0 or value>>(rows*columns):raise ValueError('matrix outside declared shape')
    return gf2_rank([(value>>(i*columns))&((1<<columns)-1) for i in range(rows)])


def lowrank_span(core,shape,target,axis):
    if type(target) is not int or target<0 or type(axis) is not int or axis not in (0,1,2):raise ValueError('invalid target/axis')
    if len(shape)!=3 or any(type(d) is not int or not 0<=d<=8 for d in shape) or len(core)!=math.prod(shape) or any(type(x) is not int or x not in (0,1) for x in core):raise ValueError('binary core with dimensions<=8 required')
    slices,other=mode_slices(core,shape,axis);space=BinaryBasis(slices);d=len(space.vectors);surplus=target-d
    if d>8:raise ValueError('this bounded reference enumerates mode rank<=8 only')
    if surplus<0:return dict(status='EXCLUDED_BY_MODE_RANK',mode_rank=d,target=target)
    cutoff=surplus+1;accepted=[];basis=BinaryBasis();witnesses=[];matrix=0;previous=0;tests=0
    for n in range(1,1<<d):
        gray=n^(n>>1);changed=gray^previous;matrix^=space.vectors[changed.bit_length()-1];previous=gray;tests+=1
        if matrix_rank(matrix,shape[other[0]],shape[other[1]])<=cutoff:
            accepted.append(gray);updated=BinaryBasis(basis.vectors+[gray])
            if len(updated.vectors)>len(basis.vectors):witnesses.append(gray)
            basis=updated
    span=len(basis.vectors)
    return dict(status='LOWRANK_SPAN_EXCLUDES' if span<d else 'BOUND_PASSED_NOT_EXISTENCE',axis=axis,mode_rank=d,target=target,
        surplus=surplus,matrix_rank_cutoff=cutoff,opposite_shape=[shape[a] for a in other],points_tested=tests,
        lowrank_points=len(accepted),lowrank_coordinate_basis=witnesses,lowrank_span_rank=span,
        space_basis=space.vectors,core_sha256=digest(dict(shape=list(shape),core=core)),
        scope='Necessary bound only on this exact residual; passing supplies no decomposition or existence claim.')
