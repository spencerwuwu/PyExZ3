from symbolic.args import *


def mypolicy(result):
    return result == 0


@policy(mypolicy)
@symbolic(c=3)
def policy(a, b, c):
    if a + b + c == 6:
        return 0
    else:
        return 1


def expected_result_set():
    return {0, 1}
