from symbolic.args import *


def myprecondition(arg):
    return arg == 2


@precondition(myprecondition)
@symbolic(a=0, b=2, c=3)
def precondition(a, b, c):
    if a + b + c == 0:
        return 0
    elif a + b + c == 6:
        return 1
    elif a == 1 and b == 1 and c == 1:
        return 2
    else:
        return 3


def expected_result_set():
    return {0, 1, 3, False}
