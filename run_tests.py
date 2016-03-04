#!/usr/bin/env python3
import os
import re
import sys
import subprocess
from optparse import OptionParser
from sys import platform as _platform


class bcolors:
    SUCCESS = '\033[32m'
    WARNING = '\033[33m'
    FAIL = '\033[31m'
    ENDC = '\033[0m'


def myprint(color, s, *printargs):
    if _platform != "win32" and sys.stdout.isatty():
        print(color, s, bcolors.ENDC, *printargs)
    else:
        print(*printargs)


usage = "usage: %prog [options] <test directory>"
parser = OptionParser()
parser.add_option("--cvc", dest="solver", action="store_const", const="--cvc", help="Use the CVC SMT solver instead of Z3")
parser.add_option("--z3str2", dest="solver", action="store_const", const="--z3str2", help="Use the Z3-str2 SMT solver instead of Z3")
parser.add_option("--z3", dest="solver", action="store_const", const="--z3", help="Use the Z3 SMT solver")
parser.add_option("--multi", dest="solver", action="store_const", const="--multi", help="Use as many different solvers as possible simultaneously")

parser.add_option("--argparse", dest="loader", action="store_const", const='--argparse')
parser.add_option("--sysargv", dest="loader", action="store_const", const='--sysargv')
parser.add_option("--optparse", dest="loader", action="store_const", const='--optparse')

parser.add_option("-n", "--workers", dest="workers", type="int", help="Run specified number of solvers in parallel.",
                  default=1)
parser.add_option("-p", "--scheduling-policy", dest="scheduling_policy", type="str",
                  help="The name of the scheduling policy used to assign solving jobs to solvers.",
                  default="central_queue")
(options, args) = parser.parse_args()

if len(args) == 0 or not os.path.exists(args[0]):
    parser.error("Please supply directory of tests")
    sys.exit(1)

test_dir = os.path.abspath(args[0])

if not os.path.isdir(test_dir):
    print("Please provide a directory of test scripts.")
    sys.exit(1)

files = [f for f in os.listdir(test_dir) if re.search(".py$", f)]

failed = []
for f in files:
    # execute the python runner for this test
    full = os.path.join(test_dir, f)
    with open(os.devnull, 'w') as devnull:
        solver = options.solver if options.solver is not None else "--z3"
        testargs = [sys.executable, "pyexz3.py", "-m 25", "-b 4", "-n", str(options.workers), "-p", options.scheduling_policy, solver]
        if options.loader is not None:
            testargs.append(options.loader)
        testargs.append(full)
        ret = subprocess.call(testargs, stdout=devnull)
    if ret == 0:
        myprint(bcolors.SUCCESS, "✓", "Test " + f + " passed.")
    else:
        failed.append(f)
        myprint(bcolors.FAIL, "✗", "Test " + f + " failed.")

if len(failed) > 0:
    print("RUN FAILED")
    print(failed)
    sys.exit(1)
else:
    sys.exit(0)
