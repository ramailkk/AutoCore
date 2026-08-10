def double_all(items):
    result = []
    for item in items:
        result.append(item * 2)
    return result


def is_even_or_odd(n):
    if n % 2 == 0:
        return "even"
    else:
        return "odd"
