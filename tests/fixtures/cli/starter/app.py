"""Count CSV records, excluding one header row."""
import csv
import sys

with open(sys.argv[1], encoding='utf-8', newline='') as stream:
    rows = csv.reader(stream)
    next(rows, None)
    print(sum(1 for _ in rows))
