import sys

def exit(a, b):
    if (a < 0):
        if (abs(a) == b):
           sys.exit(21)
        return 1
    return 2
