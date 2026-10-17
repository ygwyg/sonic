#!/usr/bin/env python3
"""A small, real program used as the payload in the Sonic demos.

It is transmitted as overlapping audio carriers, reconstructed on the
receiver and verified byte-for-byte with SHA-256. It is never executed by
the receiver.
"""

from __future__ import annotations

import math


def is_prime(n: int) -> bool:
    if n < 2:
        return False
    for d in range(2, int(math.isqrt(n)) + 1):
        if n % d == 0:
            return False
    return True


def primes(limit: int) -> list[int]:
    return [n for n in range(limit) if is_prime(n)]


def main() -> None:
    ps = primes(100)
    print(f"{len(ps)} primes below 100: {ps}")
    print("Grüße from the other side of the air gap ✓")


if __name__ == "__main__":
    main()
