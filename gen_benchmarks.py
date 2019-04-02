#!/usr/bin/python3

import os
import sys

def main(argv):
    os.system("mkdir -p smt2")
    target = argv[1]
    lines = os.popen("python pyexz3.py --cvc " + target + " | grep PRINT | sed 's/[^ ]* //'").read().splitlines()

    target_name = target.split("/")[-1].split(".py")[0]

    count = 0
    target_file = ""
    for line in lines:
        if "START" in line:
            target_file = "smt2/" + target_name + "-" + str(count) + ".smt2"
            os.system("cat /dev/null > " + target_file)
        elif "END" in line:
            print("Generated: " + target_file)
            count += 1
        else:
            os.system("echo \'" + line + "\' >> " + target_file)


if __name__ == '__main__':
    if len(sys.argv) != 2:
        print("./gen_benchmarks.py TARGET.py")
        exit(1)
    os.environ["PYTHONPATH"] = "/usr/local/lib/python3.7/site-packages"
    main(sys.argv)
