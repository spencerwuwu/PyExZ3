from symbolic.args import symbolic

@symbolic(keys="hello\ngoodbye")
def strsplitlines(keys):
    if keys.splitlines()[0] == "dog":
        return 1
    elif keys.splitlines()[1] == "cat":
        return 2
    return 0

def expected_result_set():
    return {0, 1, 2}