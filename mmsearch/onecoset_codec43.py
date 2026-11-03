"""Pure codec and independent SAT-witness checks for the unlaunched native core.

No subprocess or target query. A parent campaign must also lift and verify the
entire original matrix-multiplication tensor before accepting any replacement.
"""
from __future__ import annotations
import itertools
import hashlib

def _rank(values):
    basis={}
    for x in values:
        while x:
            p=x.bit_length()-1
            if p not in basis:basis[p]=x;break
            x^=basis[p]
    return len(basis)

def _inputs(core,shape,axis,target):
    if (len(shape)!=3 or any(type(x) is not int or not 0<=x<=8 for x in shape)
        or type(axis) is not int or axis not in range(3) or type(target) is not int or not 0<=target<=9):raise ValueError('unsupported dimensions/axis/target')
    if len(core)!=shape[0]*shape[1]*shape[2] or any(type(x) is not int or x not in (0,1) for x in core):raise ValueError('invalid exact binary core')
    other=[i for i in range(3) if i!=axis];a,b=(shape[i] for i in other);slices=[0]*shape[axis]
    for i,j,k in itertools.product(*(range(d) for d in shape)):
        xyz=(i,j,k)
        if core[(i*shape[1]+j)*shape[2]+k]:slices[xyz[axis]]^=1<<(xyz[other[0]]*b+xyz[other[1]])
    return a,b,slices,other

def encode_case(core,shape,target,axis):
    """One case line; callers prepend exactly ONECOSET43 1 and a newline."""
    a,b,slices,_=_inputs(core,shape,axis,target)
    return ' '.join(map(str,[a,b,shape[axis],target,*slices]))+'\n'

def make_request(case_id,source_sha256,core,shape,target,axis):
    """Controller ledger binding; send only line, retain the other fields."""
    if not isinstance(case_id,str) or not case_id or len(case_id)>128:raise ValueError('invalid controller case ID')
    if not isinstance(source_sha256,str) or len(source_sha256)!=64 or any(c not in '0123456789abcdef' for c in source_sha256):raise ValueError('invalid frozen source hash')
    line=encode_case(core,shape,target,axis)
    return dict(case_id=case_id,source_sha256=source_sha256,input_line=line,input_line_sha256=hashlib.sha256(line.encode()).hexdigest(),shape=list(shape),target=target,axis=axis)

def bind_response(result,request,expected_case_index,core):
    """Bind one response to one outstanding request; no bulk pipe writes.

    A local negative remains an audited-backend claim, not a global result.
    SAT always receives independent full-core checking here. The parent must
    still perform full original-MM and independent record checks after lifting.
    """
    if type(expected_case_index) is not int or expected_case_index<0 or type(result.get('case_index')) is not int or result['case_index']!=expected_case_index:raise ValueError('native/controller case index differs')
    current=make_request(request['case_id'],request['source_sha256'],core,request['shape'],request['target'],request['axis'])
    if current!=request:raise ValueError('controller source/case/input-line binding differs')
    a,b,slices,_=_inputs(core,request['shape'],request['axis'],request['target'])
    for key,value in [('left_width',a),('right_width',b),('free_width',len(slices)),('target',request['target'])]:
        if type(result.get(key)) is not int or result[key]!=value:raise ValueError('response case dimensions differ')
    status=result.get('status')
    if result.get('format')!='native-onecoset43-v1' or status not in ['SAT','LOCAL_UNSAT','UNKNOWN']:raise ValueError('unsupported native result')
    report=dict(case_id=request['case_id'],source_sha256=request['source_sha256'],input_line_sha256=request['input_line_sha256'],case_index=expected_case_index,local_status=status)
    if status=='SAT':report['core_verification']=verify_sat_result(result,core,request['shape'],request['target'],request['axis'])
    elif status=='UNKNOWN':
        if result.get('complete') is not False or result.get('products'):raise ValueError('UNKNOWN may not close a case or publish products')
    else:
        if result.get('complete') is not True or result.get('products') or type(result.get('mode_rank')) is not int or result['mode_rank']!=_rank(slices):raise ValueError('invalid local negative claim')
        d=result['mode_rank'];h=result.get('inside_rank');proof=result.get('case');target=request['target']
        if type(h) is not int or not 0<=h<=d:raise ValueError('invalid local-negative inside rank')
        if proof=='mode_rank_exceeds_target':
            if not target<d:raise ValueError('incorrect rank-lower-bound claim')
        elif proof in ['inside_points_do_not_span','no_single_coset_spans']:
            if h>=d or result.get('span_vectors_tested')!=(1<<d)-1:raise ValueError('incomplete image enumeration claim')
            if proof=='inside_points_do_not_span' and target!=d:raise ValueError('incorrect inside-only scope')
            if proof=='no_single_coset_spans' and (target!=d+1 or result.get('pair_points_tested')!=((1<<a)-1)*((1<<b)-1)):raise ValueError('incomplete pair enumeration claim')
        else:raise ValueError('unsupported local-negative proof case')
    return report

def verify_sat_result(result,core,shape,target,axis):
    """Check full core, all original slices and original factor provenance."""
    a,b,slices,other=_inputs(core,shape,axis,target);d=_rank(slices)
    if result.get('format')!='native-onecoset43-v1' or result.get('status')!='SAT' or result.get('complete') is not True:raise ValueError('complete native SAT required; UNKNOWN is never a negative')
    expected={'left_width':a,'right_width':b,'free_width':shape[axis],'target':target,'mode_rank':d,'core_entries_checked':len(core)}
    if any(type(result.get(k)) is not int or result[k]!=v for k,v in expected.items()):raise ValueError('native case binding differs')
    if result.get('full_original_slices_verified') is not True:raise ValueError('native full-slice flag missing')
    basis=result['space_basis']
    if (not isinstance(basis,list) or len(basis)!=d or any(type(x) is not int or x not in slices for x in basis)
        or _rank(basis)!=d or any(_rank([*basis,x])!=d for x in slices)):raise ValueError('invalid original image basis')
    support=result['pair_support'];columns=[];pairs=set()
    if not isinstance(support,list) or len(support)>target:raise ValueError('support bound differs')
    h=result['inside_rank'];q=result['quotient_representative']
    if type(h) is not int or not 0<=h<=d or type(q) is not int or not 0<=q<1<<(a*b):raise ValueError('invalid inside/coset dimensions')
    for j,p in enumerate(support):
        left,right,column,mask=(p[k] for k in ['left','right','column','lambda'])
        if any(type(x) is not int for x in [left,right,column,mask]) or not 0<left<1<<a or not 0<right<1<<b or not 0<=mask<1<<d:raise ValueError('invalid original point')
        actual=0
        for row in range(a):
            if left>>row&1:actual^=right<<(row*b)
        if actual!=column:raise ValueError('point is not its declared original outer product')
        residual=column
        for k,value in enumerate(basis):
            if mask>>k&1:residual^=value
        if residual!=(0 if j<h else q):raise ValueError('original point coordinate/coset differs')
        columns.append(column);pairs.add((left,right))
    if _rank(columns)!=len(columns):raise ValueError('dependent selected original points')
    products=result['products']
    if not isinstance(products,list) or len(products)>target:raise ValueError('product bound differs')
    ordered=[];actual=[0]*len(core)
    for triple in products:
        if not isinstance(triple,list) or len(triple)!=3 or any(type(x) is not int for x in triple):raise ValueError('invalid product coordinates')
        left,right,free=triple
        if not 0<left<1<<a or not 0<right<1<<b or not 0<free<1<<shape[axis] or (left,right) not in pairs:raise ValueError('product not from original selected point')
        term=[0,0,0];term[other[0]]=left;term[other[1]]=right;term[axis]=free;ordered.append(term)
        for i,j,k in itertools.product(*(range(dim) for dim in shape)):
            actual[(i*shape[1]+j)*shape[2]+k]^=(term[0]>>i&1)&(term[1]>>j&1)&(term[2]>>k&1)
    if actual!=list(core):raise ValueError('SAT witness failed independent full core tensor check')
    return dict(valid=True,products=ordered,rank=len(ordered),exact_core_entries_checked=len(core),
                original_free_slices_checked=len(slices),original_factor_witnesses_checked=len(support),
                scope='local core only; parent must separately lift/fullMM verify')
