from symbolic.args import symbolic


@symbolic(s="foo")
def strsplit_delim(s):
    if ['', ''] == s.split('#', 1):
        return 0
    return 1


def expected_result_set():
    return {0, 1}
