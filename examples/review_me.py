# Drop this file into watch/ (or `cp` it there) to trigger a CODER review.
# It has a few deliberate issues for the reviewer to catch.

def divide(a, b):
    return a / b  # no zero-division guard


def find_user(users, target):
    # O(n) lookup repeated in a loop elsewhere — could be a dict
    for u in users:
        if u["id"] == target:
            return u


def build_query(table, where):
    # SQL string interpolation — injection risk
    return "SELECT * FROM " + table + " WHERE " + where


PASSWORD = "hunter2"  # hardcoded secret
