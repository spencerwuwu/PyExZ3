from symbolic.args import symbolic


@symbolic(s="foo")
def strlower(s):
    if s.lower() == "hello":
        return 0
    if "X" in s and "x" in s.lower():
        return 1
    return 2


def expected_result_set():
    return {0, 1, 2}
