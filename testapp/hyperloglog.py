from __future__ import annotations

from collections.abc import Iterable
from math import floor, log


class HyperLogLog:
    """Reference implementation of HyperLogLog for testing purposes"""

    def __init__(self, precision: int) -> None:
        """
        precision: number of bits to use for the hash bucketing
        """
        self.n_buckets = 1 << precision
        self.buckets: list[int | None] = [None] * self.n_buckets

    def add(self, hashed_value: int) -> None:
        """
        hashed_value: the hashed value to add to the HyperLogLog
        """
        bucket = hashed_value & (self.n_buckets - 1)
        most_significant_bit = self._get_most_significant_bit(hashed_value)

        # for some reason mypy doesn't understand that once we've checked the bucket is not None
        # the comparison will always be valid
        if self.buckets[bucket] is None or most_significant_bit > self.buckets[bucket]:  # type: ignore
            self.buckets[bucket] = most_significant_bit

    def _alpha(self) -> float:
        """
        Calculates the alpha value for the given precision
        """
        if self.n_buckets == 16:
            return 0.673  # for precision 4
        elif self.n_buckets == 32:
            return 0.697  # for precision 5
        elif self.n_buckets == 64:
            return 0.709  # for precision 6
        else:
            return 0.7213 / (1 + 1.079 / self.n_buckets)  # for precision >= 7

    def _get_most_significant_bit(self, hashed_value: int) -> int:
        """
        Returns the position of the most significant bit
        """
        return 31 - floor(log(hashed_value, 2))

    def _count_zero_buckets(self) -> int:
        """
        Returns the number of non-zero buckets
        """
        return sum(1 for bucket in self.buckets if bucket is None)

    def _yield_non_zero_buckets(self) -> Iterable[int]:
        for b in self.buckets:
            if b is not None:
                yield b

    def cardinality(self) -> int:
        n_zero_buckets = self._count_zero_buckets()
        alpha = self._alpha()

        raw_estimate = round(
            ((self.n_buckets**2) * alpha)
            / float(
                +n_zero_buckets
                + sum((2 ** (-1 * msb)) for msb in self._yield_non_zero_buckets())
            )
        )
        if raw_estimate < 2.5 * self.n_buckets and n_zero_buckets:
            return round(
                alpha * (self.n_buckets * log(self.n_buckets / n_zero_buckets, 2))
            )

        return raw_estimate
