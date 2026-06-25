"""generate_series virtual table (table-valued function)."""

from typing import Any
from pysqlite.virtualtables import VirtualTable, register_module


class GenerateSeries(VirtualTable):
    name = 'generate_series'
    module = 'generate_series'
    columns = ['value']

    def __init__(self, name: str, args: list[str], config: dict[str, Any]):
        self._name = name
        self._start = 1
        self._stop = 100
        self._step = 1
        if args:
            try:
                self._stop = int(args[0])
            except (ValueError, IndexError):
                pass
        if len(args) >= 2:
            try:
                self._start = int(args[1])
            except ValueError:
                pass
        if len(args) >= 3:
            try:
                self._step = int(args[2])
            except ValueError:
                pass
        self._current = self._start

    def close(self):
        pass

    def reset(self):
        self._current = self._start

    def next(self) -> dict[str, Any] | None:
        if self._step > 0 and self._current > self._stop:
            return None
        if self._step < 0 and self._current < self._stop:
            return None
        row = {'value': self._current}
        self._current += self._step
        return row

    def column_count(self) -> int:
        return 1

    def column_name(self, idx: int) -> str:
        return 'value'

    def rowid(self) -> int:
        return self._current - self._step


register_module('generate_series', GenerateSeries)
