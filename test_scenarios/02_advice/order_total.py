"""Order total calculator. Scenario: ADVICE — correct code, but a
non-blocking style opinion is available (manual accumulator loop instead
of sum()). Opening a PR that adds/touches this file should classify as
"advice"."""


def calculate_total(prices):
    total = 0
    for price in prices:
        total = total + price
    return total
