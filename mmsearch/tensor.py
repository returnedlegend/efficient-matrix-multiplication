"""Exact trace-form matrix multiplication tensors and honest baseline schemes.

Coordinates are row-major.  The third factor is the trace functional: w[k*n+i]
contributes to output[i][k].  Thus T[(i,j),(j,k),(k,i)] = 1.
"""

from __future__ import annotations


def tensor_index(a: int, b: int, c: int, n: int = 5) -> int:
    """Flatten three coordinates, each in a vector of length n**2."""
    return (a * n * n + b) * n * n + c


def multiplication_tensor(n: int = 5) -> list[int]:
    if type(n) is not int or n < 1:
        raise ValueError("dimension must be a positive integer")
    result = [0] * n**6
    for i in range(n):
        for j in range(n):
            for k in range(n):
                result[tensor_index(i * n + j, j * n + k, k * n + i, n)] = 1
    return result


def _candidate(n: int, field: int, terms: list[dict], method: str) -> dict:
    if type(field) is not int or field not in (0, 2):
        raise ValueError("field must be 2 (F2) or 0 (integers)")
    if field == 2:
        terms = [{axis: [v % 2 for v in term[axis]] for axis in ("u", "v", "w")}
                 for term in terms]
    return {"field": field, "dimension": n, "terms": terms,
            "metadata": {"method": method, "rank": len(terms),
                         "third_factor": "trace: w[k*n+i] contributes to output[i][k]"}}


def naive_candidate(n: int = 5, field: int = 2) -> dict:
    """Return the n**3 scalar-product certificate."""
    if type(n) is not int or n < 1:
        raise ValueError("dimension must be a positive integer")
    terms = []
    for i in range(n):
        for j in range(n):
            for k in range(n):
                u, v, w = ([0] * (n * n) for _ in range(3))
                u[i * n + j] = v[j * n + k] = w[k * n + i] = 1
                terms.append({"u": u, "v": v, "w": w})
    return _candidate(n, field, terms, "naive")


def _linear_sum(left: dict[int, int], right: dict[int, int], sign: int = 1) -> dict[int, int]:
    result = dict(left)
    for key, value in right.items():
        result[key] = result.get(key, 0) + sign * value
        if not result[key]:
            del result[key]
    return result


def _strassen(a: list[list[dict]], b: list[list[dict]]) -> list[tuple[dict, dict, list[list[int]]]]:
    """Return products of original input linear forms and output weights."""
    size = len(a)
    if size == 1:
        return [(a[0][0], b[0][0], [[1]])]
    h = size // 2
    def blocks(matrix):
        return [
            [[matrix[i + di][j + dj] for j in range(h)] for i in range(h)]
            for di, dj in ((0, 0), (0, h), (h, 0), (h, h))
        ]
    def add(x, y, sign=1):
        return [[_linear_sum(x[i][j], y[i][j], sign) for j in range(h)] for i in range(h)]
    a11, a12, a21, a22 = blocks(a)
    b11, b12, b21, b22 = blocks(b)
    products = [
        (add(a11, a22), add(b11, b22), (1, 0, 0, 1)),
        (add(a21, a22), b11, (0, 0, 1, -1)),
        (a11, add(b12, b22, -1), (0, 1, 0, 1)),
        (a22, add(b21, b11, -1), (1, 0, 1, 0)),
        (add(a11, a12), b22, (-1, 1, 0, 0)),
        (add(a21, a11, -1), add(b11, b12), (0, 0, 0, 1)),
        (add(a12, a22, -1), add(b21, b22), (1, 0, 0, 0)),
    ]
    result = []
    for left, right, destinations in products:
        for u, v, small_weights in _strassen(left, right):
            weights = [[0] * size for _ in range(size)]
            for weight, (di, dj) in zip(destinations, ((0, 0), (0, h), (h, 0), (h, h))):
                for i in range(h):
                    for j in range(h):
                        weights[di + i][dj + j] = weight * small_weights[i][j]
            result.append((u, v, weights))
    return result


def strassen_candidate(n: int = 5, field: int = 2) -> dict:
    """Use Strassen on the largest power-of-two block, naive elsewhere.

    For n=5 the rank is 49 + (125 - 64) = 110.
    """
    if type(n) is not int or n < 1:
        raise ValueError("dimension must be a positive integer")
    block = 1 << (n.bit_length() - 1)
    a = [[{i * n + j: 1} for j in range(block)] for i in range(block)]
    b = [[{i * n + j: 1} for j in range(block)] for i in range(block)]
    terms = []
    for left, right, weights in _strassen(a, b):
        u, v, w = ([0] * (n * n) for _ in range(3))
        for index, value in left.items():
            u[index] = value
        for index, value in right.items():
            v[index] = value
        for i in range(block):
            for k in range(block):
                w[k * n + i] = weights[i][k]
        terms.append({"u": u, "v": v, "w": w})
    for term in naive_candidate(n, field=0)["terms"]:
        i, j = divmod(term["u"].index(1), n)
        _, k = divmod(term["v"].index(1), n)
        if max(i, j, k) >= block:
            terms.append(term)
    return _candidate(n, field, terms, "block-strassen")
