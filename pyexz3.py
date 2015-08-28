# Copyright: see copyright.txt

import logging
import time
from optparse import OptionParser

from symbolic.loader import *
from symbolic.explore import ExplorationEngine

print("PyExZ3 (Python Exploration with Z3)")

sys.path = [os.path.abspath(os.path.join(os.path.dirname(__file__)))] + sys.path

usage = "usage: %prog [options] <path to a *.py file>"
parser = OptionParser(usage=usage)

parser.add_option("-l", "--log", dest="logfile", action="store", help="Save log output to a file", default="")
parser.add_option("-s", "--start", dest="entry", action="store", help="Specify entry point", default="")
parser.add_option("-g", "--graph", dest="dot_graph", action="store_true", help="Generate a DOT graph of execution tree")
parser.add_option("-t", "--timeout", dest="timeout", type="int", help="Time in seconds to terminate the symbolic execution", default=None)
parser.add_option("--solvetimeout", dest="solvetimeout", type="float", help="Time in seconds to terminate a query to the SMT", default=30)
parser.add_option("-m", "--max-iters", dest="max_iters", type="int", help="Run specified number of iterations",
                  default=0)
parser.add_option("--cvc", dest="cvc", action="store_true", help="Use the CVC SMT solver instead of Z3", default=False)
parser.add_option("--z3", dest="cvc", action="store_false", help="Use the Z3 SMT solver")

(options, args) = parser.parse_args()

if not (options.logfile == ""):
    logging.basicConfig(filename=options.logfile, level=logging.DEBUG)

if len(args) == 0 or not os.path.exists(args[0]):
    parser.error("Missing app to execute")
    sys.exit(1)

solver = "cvc" if options.cvc else "z3"
startime = time.clock() # depreciated in Python 3.3, replace with perf_counter or process_time

filename = os.path.abspath(args[0])

# Get the object describing the application
app = loaderFactory(filename, options.entry)
if app is None:
    sys.exit(1)

print("Exploring " + app.getFile() + "." + app.getEntry())

result = None
try:
    engine = ExplorationEngine(app.createInvocation(), solver=solver, solvetimeout=options.solvetimeout)
    generatedInputs, returnVals, path = engine.explore(options.max_iters, options.timeout)
    # check the result
    result = app.executionComplete(returnVals)
    endtime = time.clock()
    print("Execution time: {0:.2f} seconds".format(endtime - startime))
    print("Total solver time: {0:.2f} seconds".format(engine.solver.solvertime))
    # instrumentation time is only valid in Unix Python environments due to the inconsistent behavior of time.clock
    print("Instrumentation time: {0:.2f} seconds".format((endtime - startime) - engine.solver.solvertime))
    # output DOT graph
    if options.dot_graph:
        file = open(filename + ".dot", "w")
        file.write(path.toDot())
        file.close()

except ImportError as e:
    # createInvocation can raise this
    logging.error(e)
    sys.exit(1)

if result is None or result:
    sys.exit(0)
else:
    sys.exit(1)
