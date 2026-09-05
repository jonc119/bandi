from __future__ import annotations

import csv
import unicodedata


def csv_text(value: object) -> object:
    if not isinstance(value, str):
        return value
    normalized = unicodedata.normalize("NFKC", value)
    candidate = normalized.lstrip(" \t\r\n\v\f\ufeff\u200b")
    if candidate.startswith(("=", "+", "-", "@")) or value.startswith(("\t", "\r", "\n")):
        return "'" + value
    return value


class SafeCsvWriter:
    def __init__(self, stream):
        self._writer = csv.writer(stream)

    def writerow(self, values):
        return self._writer.writerow(csv_text(value) for value in values)
