"""Separate rank<=3 necessary image-span filter for d9 / target11 prep."""
from .compact_sat import BinaryBasis
from .compact_coset43 import mode_slices,_insert,digest


def matrix_rank_at_most_three(value,rows,columns):
    """Return exact0..3, or4 meaning rank>=4; use original matrix rows."""
    if any(type(v) is not int or v<0 for v in (value,rows,columns)) or value>>(rows*columns):raise ValueError('invalid binary matrix')
    pivots={};mask=(1<<columns)-1
    for i in range(rows):
        if _insert(pivots,(value>>(i*columns))&mask) and len(pivots)==4:return 4
    return len(pivots)


def rank_three_span(core,shape,axis,cancelled=None):
    """Necessary only: CP<=11 implies all rank<=3 matrices span a d9 image."""
    if len(shape)!=3 or any(type(d) is not int or not 0<=d<=9 for d in shape) or len(core)!=shape[0]*shape[1]*shape[2] or any(type(v) is not int or v not in (0,1) for v in core) or type(axis) is not int or axis not in (0,1,2):raise ValueError('invalid bounded core/axis')
    slices,other=mode_slices(core,shape,axis);space=BinaryBasis(slices)
    if len(space.vectors)!=9:raise ValueError('rank-three filter reviewed for actual d9 image only')
    stats=dict(axis=axis,mode_rank=9,target=11,matrix_rank_cutoff=3,core_sha256=digest(dict(shape=list(shape),core=core)),space_basis=space.vectors,opposite_shape=[shape[j] for j in other])
    basis={};witness=[];accepted=0;value=0;previous=0
    def finish(status,tests):
        if cancelled and cancelled():status='UNKNOWN'
        return dict(stats,status=status,complete=status!='UNKNOWN',points_tested=tests,lowrank_points=accepted,lowrank_span_rank=len(basis),lowrank_coordinate_basis=witness,
            enumeration_complete=tests==511,passing_is_not_existence=True)
    if cancelled and cancelled():return finish('UNKNOWN',0)
    for n in range(1,512):
        if cancelled and cancelled():return finish('UNKNOWN',n-1)
        gray=n^(n>>1);changed=gray^previous;value^=space.vectors[changed.bit_length()-1];previous=gray
        if matrix_rank_at_most_three(value,shape[other[0]],shape[other[1]])<=3:
            accepted+=1
            if _insert(basis,gray):witness.append(gray)
            if len(basis)==9:return finish('BOUND_PASSED_NOT_EXISTENCE',n)
    return finish('LOWRANK_SPAN_EXCLUDES',511)
