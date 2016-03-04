from symbolic.args import symbolic


@symbolic(s="foo")
def strlist(s):
    if s == []:
        return 0
    else:
        return 1


def expected_result():
    return [1]
