"""Independent exact counts and cursors for finite streamed triple families."""
from bisect import bisect_left
from math import comb


def choose3(n):
    return comb(n, 3) if n >= 3 else 0


def ordinal(count, begin, triple):
    i, j, k = triple
    if not 0 <= begin <= i < j < k < count:
        raise ValueError('invalid stream triple')
    return (choose3(count-begin)-choose3(count-i) +
            (j-i-1)*(2*count-i-j-2)//2 + k-j-1)


def unrank(count, begin, end, position):
    total = choose3(count-begin)-choose3(count-end)
    if not 0 <= position < total:
        raise ValueError('base cursor outside stream')
    low, high = begin, end
    while low+1 < high:
        middle = (low+high)//2
        if choose3(count-begin)-choose3(count-middle) <= position:
            low = middle
        else:
            high = middle
    i = low
    left = position-(choose3(count-begin)-choose3(count-i))
    low, high = i+1, count-1
    while low+1 < high:
        middle = (low+high)//2
        if (middle-i-1)*(2*count-i-middle-2)//2 <= left:
            low = middle
        else:
            high = middle
    j = low
    return i, j, j+1+left-(j-i-1)*(2*count-i-j-2)//2


def stream_cursor(count, begin, end, exclusions, row):
    """Return (base ordinal, next triple) after exactly row retained triples."""
    excluded = sorted(ordinal(count, begin, triple) for triple in exclusions)
    base_total = choose3(count-begin)-choose3(count-end)
    if not 0 <= row <= base_total-len(excluded):
        raise ValueError('retained cursor outside stream')
    if row == base_total-len(excluded):
        return base_total, (-1, -1, -1)
    low, high = 0, base_total
    while low < high:
        middle = (low+high)//2
        if middle-bisect_left(excluded, middle) < row:
            low = middle+1
        else:
            high = middle
    position = low
    excluded_set = set(excluded)
    while position in excluded_set:
        position += 1
    return position, unrank(count, begin, end, position)


def parse_catalog(raw, count):
    words = raw.decode().split()
    if not words:
        raise ValueError('empty triple catalog')
    if words[0] == 'MMKTRIPLES1':
        size = int(words[1]); values = list(map(int, words[2:]))
        if not 0 <= size <= 2000000 or len(values) != 3*size:
            raise ValueError('invalid explicit catalog size')
        begin, end = 0, count-2
        base_total = size
    elif words[0] == 'MMKTRIPLESTREAM1':
        declared, begin, end, size = map(int, words[1:5])
        if declared != count or not 0 <= begin <= end <= count-2 or not 0 <= size <= 2000000:
            raise ValueError('invalid streamed catalog header')
        values = list(map(int, words[5:]))
        if len(values) != 3*size:
            raise ValueError('invalid streamed exclusion size')
        base_total = choose3(count-begin)-choose3(count-end)
    else:
        raise ValueError('unknown triple catalog schema')
    rows = [tuple(values[i:i+3]) for i in range(0, len(values), 3)]
    if len(set(rows)) != size or any(not 0 <= i < j < k < count for i, j, k in rows):
        raise ValueError('invalid or duplicate triple')
    streamed = words[0] == 'MMKTRIPLESTREAM1'
    if streamed and any(not begin <= row[0] < end for row in rows):
        raise ValueError('exclusion outside streamed family')
    return dict(selected=base_total-size if streamed else size, base_triples_total=base_total,
                excluded_triples=size if streamed else 0, schema=words[0],
                first_begin=begin, first_end=end, full_unordered_family=False,
                catalog_order='lexicographic triples, excluding explicitly listed completed triples' if streamed else 'explicit row order')


def stream_bytes(count, begin, end, exclusions=()):
    rows = sorted(set(tuple(t) for t in exclusions))
    raw = (f'MMKTRIPLESTREAM1 {count} {begin} {end} {len(rows)}\n' +
           ''.join(' '.join(map(str, t))+'\n' for t in rows)).encode()
    return raw, parse_catalog(raw, count)
