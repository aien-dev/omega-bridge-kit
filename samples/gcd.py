"""Sample original: Euclid's algorithm in Python (floor-mod semantics)."""


def gcd(a, b):
    while b != 0:
        t = a % b
        a = b
        b = t
    return a


def lcm(a, b):
    return a // gcd(a, b) * b


if __name__ == "__main__":
    print(gcd(48, 18), lcm(4, 6))
