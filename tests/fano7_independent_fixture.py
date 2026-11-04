"""Synthetic11³ Fano-only rank14 tensor; no matrix-multiplication source."""


def planted_fano_b7():
    width=11
    pair=lambda a,b:sum(b<<(width*i) for i in range(width) if a>>i&1)
    backbone=[(1<<7,1<<j) for j in range(7,11)]+[(1<<i,1<<7) for i in range(8,11)]
    points=[(1<<i,1<<i) for i in range(7)]
    circuits=[(0,1,3),(0,2,4),(1,2,5),(0,1,2,6)]
    slices=[pair(a,b) for a,b in backbone]
    for circuit in circuits:
        value=0
        for i in circuit:value^=pair(*points[i])
        slices.append(value)
    core=[(value>>bit)&1 for value in slices for bit in range(width*width)]
    products=[(1<<i,a,b) for i,(a,b) in enumerate(backbone)]
    for i,(a,b) in enumerate(points):
        free=sum(1<<(7+j) for j,circuit in enumerate(circuits) if i in circuit)
        products.append((free,a,b))
    return dict(core=core,shape=[11]*3,slices=slices,
                backbone_rankone_points=[dict(left=a,right=b,matrix=pair(a,b)) for a,b in backbone],
                fano_rankone_points=[dict(left=a,right=b,matrix=pair(a,b)) for a,b in points],
                circuits=circuits,products=products,expected_cp_rank=14,
                scope='Synthetic partialtensor only, not an N5matrixmultiplication certificate.')
