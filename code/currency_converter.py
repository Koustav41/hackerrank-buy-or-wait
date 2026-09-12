"""
currency_converter.py
Fixed-rate FX converter for the Buy or Wait? challenge.

Available pairs: EUR->USD, EUR->ZAR, USD->EUR, USD->IDR, USD->INR
For cross-rates (e.g. ZAR->INR), use BFS over all direct and inverse pairs.
Use the rate on or most recently before the target date.
"""

from datetime import date
from typing import List, Optional
from data_loader import ExchangeRate
from collections import deque


class CurrencyConverter:
    def __init__(self, rates: List[ExchangeRate]):
        # Build lookup: (from_currency, to_currency) -> sorted list of (rate_date, rate)
        self._rates = {}
        for r in rates:
            key = (r.from_currency, r.to_currency)
            if key not in self._rates:
                self._rates[key] = []
            self._rates[key].append((r.rate_date, r.rate))
        # Sort by date
        for key in self._rates:
            self._rates[key].sort(key=lambda x: x[0])

    def _get_direct_rate(self, from_cur: str, to_cur: str, on_date: date) -> Optional[float]:
        """Get the most recent rate on or before on_date for a direct pair."""
        key = (from_cur, to_cur)
        if key not in self._rates:
            return None
        entries = self._rates[key]
        # Find the latest entry where rate_date <= on_date
        best_rate = None
        for entry_date, rate in entries:
            if entry_date <= on_date:
                best_rate = rate
            else:
                break
        # If none found (all entries are after on_date), use earliest
        if best_rate is None and entries:
            best_rate = entries[0][1]
        return best_rate

    def get_rate(self, from_cur: str, to_cur: str, on_date: date) -> float:
        """
        Get conversion rate from from_cur to to_cur on on_date.
        Uses BFS over all direct and inverse pairs to find multi-hop routes.
        """
        if from_cur == to_cur:
            return 1.0

        # Build adjacency: cur -> list of (neighbor, rate)
        edges = {}
        for (fc, tc), rate_list in self._rates.items():
            rate = None
            for entry_date, r in rate_list:
                if entry_date <= on_date:
                    rate = r
                else:
                    break
            if rate is None and rate_list:
                rate = rate_list[0][1]
            if rate is None:
                continue
            if fc not in edges:
                edges[fc] = []
            if tc not in edges:
                edges[tc] = []
            edges[fc].append((tc, rate))          # direct
            if rate != 0:
                edges[tc].append((fc, 1.0 / rate))  # inverse

        # BFS
        queue = deque([(from_cur, 1.0)])
        visited = {from_cur}
        while queue:
            cur, cum_rate = queue.popleft()
            if cur == to_cur:
                return cum_rate
            for neighbor, rate in edges.get(cur, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, cum_rate * rate))

        raise ValueError(f"Cannot find exchange rate: {from_cur} -> {to_cur} on {on_date}")

    def convert(self, amount: float, from_cur: str, to_cur: str, on_date: date) -> float:
        """Convert amount from from_cur to to_cur on on_date."""
        if from_cur == to_cur:
            return amount
        rate = self.get_rate(from_cur, to_cur, on_date)
        return amount * rate


if __name__ == "__main__":
    from data_loader import load_all
    data = load_all()
    converter = CurrencyConverter(data.exchange_rates)
    test_date = date(2024, 3, 15)
    print(f"USD -> ZAR on {test_date}: {converter.convert(1.0, 'USD', 'ZAR', test_date):.4f}")
    print(f"ZAR -> USD on {test_date}: {converter.convert(1.0, 'ZAR', 'USD', test_date):.6f}")
    print(f"ZAR -> INR on {test_date}: {converter.convert(1.0, 'ZAR', 'INR', test_date):.4f}")
    print(f"EUR -> INR on {test_date}: {converter.convert(1.0, 'EUR', 'INR', test_date):.4f}")
    print(f"INR -> IDR on {test_date}: {converter.convert(100.0, 'INR', 'IDR', test_date):.4f}")
    print(f"IDR -> ZAR on {test_date}: {converter.convert(1000.0, 'IDR', 'ZAR', test_date):.4f}")
