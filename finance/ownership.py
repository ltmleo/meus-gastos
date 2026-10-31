"""Resolve abbreviations printed by the bank without guessing gender from names."""
from finance.classification import normalized

def same_holder(left, right):
    a, b = normalized(left).split(), normalized(right).split()
    if len(a) < 2 or len(a) != len(b) or a[0] != b[0]:
        return False
    return all(x == y or (min(len(x), len(y)) >= (3 if i == len(a)-1 else 1)
                         and (x.startswith(y) or y.startswith(x)))
               for i, (x, y) in enumerate(zip(a, b)))

def canonical_holders(names):
    result = {}
    for name in names:
        candidates = [other for other in names if same_holder(name, other) or name == other]
        result[name] = max(candidates, key=len)
    return result
