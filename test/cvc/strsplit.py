from symbolic.args import symbolic


@symbolic(s="foo")
def strsplit(s):
    if ['a', 'b'] == s.split(None, 1):
        return 0
    return 1


def expected_result_set():
    return {0, 1}
