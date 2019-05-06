from symbolic.args import symbolic, concrete

def summing(a, b):
    c = a + b
    d = c + 2 * len("ccc")
    return d

def mytest(in1, in2):
    if in1 ==  0:
        in1 = in1 + 3
        if in1 < in2:
            return 0
    elif in1 == 1:
        in1 = in1 - in2 
        if in1 < in2:
            return 1
    else:
        return 9
    
    return 10

def expected_result():
	return [0, 1, 9, 10, 10]

