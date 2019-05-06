from symbolic.args import symbolic, concrete

@symbolic(in1="XIV")
#@concrete(in1="XIV")
def romanToInt(in1):
    num = {'I':1, 'V':5, 'X':10, 'L':50, 'C':100, 'D':500, 'M':1000, 'E':0 }

    for val in in1:
        if val not in num:
            return -1

    L = len(in1)
    in1 = in1 + "E"
    sum = 0

    for i in range (0,L):
        if num[in1[i]] >= num[in1[i+1]]:
            sum = sum + num[in1[i]]
        else:
            sum = sum - num[in1[i]]

    return sum

@symbolic(in1="XIV")
def different_name(in1):
    num = {'I':1, 'V':5, 'X':10, 'L':50, 'C':100, 'D':500, 'M':1000, 'E':0 }

    for val in in1:
        if val not in num:
            return -1

    L = len(in1)
    in1 = in1 + "E"
    sum = 0

    for i in range (0,L):
        if num[in1[i]] >= num[in1[i+1]]:
            sum = sum + num[in1[i]]
        else:
            sum = sum - num[in1[i]]

    return sum
