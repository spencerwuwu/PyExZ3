#!/usr/bin/env python3
# Copyright: see copyright.txt

import logging
import pickle
import time
from multiprocessing import freeze_support
import sys
import os
from sys import platform, setrecursionlimit
from optparse import OptionParser
from optparse import OptionGroup
from symbolic.loader import loaderFactory
from symbolic.explore import ExplorationEngine

def main():
    # OS X support: allow dylibs to see each other; needed by SWIG
    from platform import python_implementation
    if python_implementation() == 'CPython' and platform == 'darwin':
        from ctypes import RTLD_GLOBAL
        sys.setdlopenflags(RTLD_GLOBAL)

    sys.setrecursionlimit(10000)

    print("PyExZ3 (Python Exploration with Z3)")

    sys.path = [os.path.abspath(os.path.join(os.path.dirname(__file__)))] + sys.path

    usage = "usage: %prog [options] <path to a *.py file>"
    parser = OptionParser(usage=usage)

    # Setup
    setup_group = OptionGroup(parser, "Exploration Setup")
    setup_group.add_option("-s", "--start", dest="entry", action="store", help="Specify entry point", default="")
    setup_group.add_option("--cvc", dest="solver", action="store_const", const="cvc", help="Use the CVC SMT solver instead of Z3")
    setup_group.add_option("--z3str2", dest="solver", action="store_const", const="z3str2", help="Use the Z3-str2 SMT solver instead of Z3")
    setup_group.add_option("--z3", dest="solver", action="store_const", const="z3", help="Use the Z3 SMT solver")
    setup_group.add_option("--multi", dest="solver", action="store_const", const="multi", help="Use as many different solvers as possible simultaneously")
    parser.add_option_group(setup_group)

    # Configuration
    configuration_group = OptionGroup(parser, "Exploration Configuration")
    configuration_group.add_option("-n", "--workers", dest="workers", type="int",
                                   help="Run specified number of solvers in parallel",
                                   default=1)
    configuration_group.add_option("-p", "--scheduling-policy", dest="scheduling_policy", type="str",
                                   help="The name of the scheduling policy used to assign solving jobs to solvers.",
                                   default="central_queue")
    parser.add_option_group(configuration_group)

    # Input Detection
    input_detection_group = OptionGroup(parser, "Input Detection")
    input_detection_group.add_option("--argparse", dest="loader", action="store_const", const='argparse')
    input_detection_group.add_option("--sysargv", dest="loader", action="store_const", const='sysargv')
    input_detection_group.add_option("--optparse", dest="loader", action="store_const", const='optparse')
    parser.add_option_group(input_detection_group)

    # Limits
    limits_group = OptionGroup(parser, "Exploration Limits")
    limits_group.add_option("-t", "--exploration-timeout", dest="explorationtimeout", type="int",
                            help="Time in seconds to terminate the concolic execution", default=None)
    limits_group.add_option("--solve-timeout", dest="solvetimeouts", action='append', type=float,
                            help="Time in seconds to terminate a query to the SMT", default=None)
    limits_group.add_option("--path-timeout", dest="pathtimeout", type="int",
                            help="Maximum solving time to traverse down a single path", default=None)
    limits_group.add_option("-b", "--coverage-pruning", dest="coverage_pruning", type="int",
                            help="Prune paths after no coverage increase for the specified number of inputs generated.",
                            default=None)
    limits_group.add_option("-m", "--max-iters", dest="max_iters", type="int", help="Run specified number of iterations",
                            default=0)
    parser.add_option_group(limits_group)

    # Serialization and Logging
    logging_group = OptionGroup(parser, "Serialization and Logging")
    logging_group.add_option("-l", "--log", dest="logfile", action="store", help="Save log output to a file", default="")
    logging_group.add_option("-g", "--graph", dest="execution_graph", action="store",
                             help="The file to save the serialized execution tree")
    logging_group.add_option("-d", "--dot", dest="dot_graph", action="store",
                             help="The file to save a DOT graph of execution tree")
    logging_group.add_option("-q", "--query-store", dest="query_store", type="str",
                             help="The folder to store generated and the execution graph, "
                                  "currently only CVC supports full query serialization")
    logging_group.add_option('--debug', help="Enables debugging output.", action="store_true", dest="debug")
    parser.add_option_group(logging_group)

    (options, args) = parser.parse_args()

    debuglogging = options.debug

    if debuglogging:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.INFO

    if not (options.logfile == ""):
        logging.basicConfig(filename=options.logfile, level=loglevel, format='%(asctime)s\t%(levelname)s\t%(message)s',
                            datefmt='%m/%d/%Y %I:%M:%S %p')

    if len(args) == 0 or not os.path.exists(args[0]):
        parser.error("Missing app to execute")
        sys.exit(1)

    solver = options.solver if options.solver is not None else "z3"
    solvetimeouts = options.solvetimeouts
    query_store = options.query_store
    scheduling_policy = options.scheduling_policy
    starttime_cpu = time.process_time()
    starttime_wall = time.time()
    filename = os.path.abspath(args[0])

    # Get the object describing the application
    app = loaderFactory(filename, options.entry, loader=options.loader)
    if app is None:
        sys.exit(1)

    print("Exploring " + app.filename + "." + app.entrypoint)

    engine = ExplorationEngine(app.createInvocation(), solver=solver, query_store=query_store, solvetimeouts=solvetimeouts,
                               workers=options.workers, scheduling_policy=scheduling_policy,
                               pathtimeout=options.pathtimeout, coverage_pruning=options.coverage_pruning)
    generatedInputs, return_values, path = engine.explore(options.max_iters, options.explorationtimeout)
    # check the result
    result = app.execution_complete(return_values)
    endtime_cpu = time.process_time()
    endtime_wall = time.time()
    print("Execution time: {0:.2f} seconds".format(endtime_wall - starttime_wall))
    print("Solver CPU: {0:.2f} seconds".format(engine.total_solve_time))
    instrumentation_time = endtime_cpu - starttime_cpu
    print("Instrumentation CPU: {0:.2f} seconds".format(instrumentation_time))
    print("Path coverage: {} paths".format(len(generatedInputs)))
    total_lines, executed_lines, executed_branches = engine.coverage_statistics()
    print("Line coverage: {}/{} lines ({:.2%})".format(executed_lines, total_lines, (executed_lines/total_lines) if total_lines > 0 else 0))
    print("Branch coverage: {} branches".format(executed_branches))
    print("Exceptions: {} exceptions raised".format(len({e for e in return_values if
                                                         isinstance(e, Exception) and hasattr(e, 'id')})))
    print("Triaged exceptions: {} triaged exceptions raised".format(len({e.id for e in return_values if
                                                                         isinstance(e, Exception) and hasattr(e, 'id')})))
    # output DOT graph
    if options.dot_graph is not None:
        with open(options.dot_graph, "w") as f:
            f.write(path.toDot())

    # output serialized exploration graph
    if options.execution_graph is not None:
        pickle.dump(path, open(options.execution_graph, "wb"))

    if not result and options.loader == None:
        sys.exit(1)

if __name__ == '__main__':
    if platform.startswith('win'):
        freeze_support()
    main()