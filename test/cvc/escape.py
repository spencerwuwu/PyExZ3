from symbolic.args import symbolic


@symbolic(string="foo")
def escape(string):
    if string and '\\' not in string and string.find(':') > 0:
        return 0
    elif '"' in string:
        return 1
    else:
        return 2


def expected_result_set():
    return {0, 1, 2}
