import subprocess


def check(user: str, password_expr: str) -> bool:
    return eval(password_expr) == user
