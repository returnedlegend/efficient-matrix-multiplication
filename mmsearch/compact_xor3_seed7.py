"""Exact F2 odd-parent crossover and deterministic shared-two-factor reduction."""
from collections import defaultdict

def canonical(terms):
    state=set()
    for term in terms:
        term=tuple(term)
        if len(term)!=3 or any(type(value)is not int or value<0 for value in term):raise ValueError('three nonnegative integer factor masks required')
        if not all(term):continue
        if term in state:state.remove(term)
        else:state.add(term)
    return tuple(sorted(state))

def xor_three(parents):
    if len(parents)!=3:raise ValueError('exactly three tensor parents required')
    return canonical(term for parent in parents for term in parent)

def reduce_shared_two(terms,poll=None):
    """Each rewrite is (a,b,c)+(a,b,d)=(a,b,c XOR d), modulo GF2."""
    state=set(canonical(terms));moves=[]
    while True:
        if poll:poll()
        selected=None
        for free in range(3):
            seen={};other=[axis for axis in range(3)if axis!=free]
            for term in sorted(state):
                key=(term[other[0]],term[other[1]])
                if key in seen:selected=(free,seen[key],term);break
                seen[key]=term
            if selected:break
        if selected is None:return tuple(sorted(state)),moves
        free,left,right=selected;merged=list(left);merged[free]^=right[free];merged=tuple(merged)
        before=len(state);state.remove(left);state.remove(right)
        cancelled=False
        if all(merged):
            if merged in state:state.remove(merged);cancelled=True
            else:state.add(merged)
        if len(state)>=before:raise AssertionError('exact reduction did not strictly decrease support')
        moves.append(dict(free_axis=free,parents=[left,right],merged=merged,cancelled_existing=cancelled,
            before_rank=before,after_rank=len(state)))
