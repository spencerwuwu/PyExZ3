__author__ = "Peter Chapman"

import sys
import logging
import pickle
import argparse
from queue import PriorityQueue


def main():
    argparser = argparse.ArgumentParser(description="Simulates query selection strategies on serialized exploration "
                                                    "graphs")
    argparser.add_argument('explorationgraph', help="The serialized exploration graph on which to simulate strategies.")
    argparser.add_argument('-d', '--debug', help="Enables debugging output.", action="store_true")
    argparser.add_argument('-v', '--verbose', help="Enables verbose output. Debugging output includes verbose output.",
                           action='store_true')

    args = argparser.parse_args()

    debuglogging = args.debug
    verboselogging = args.verbose

    if debuglogging:
        loglevel = logging.DEBUG
    elif verboselogging:
        loglevel = logging.INFO
    else:
        loglevel = logging.WARNING

    FORMAT = '%(asctime)s - %(levelname)s : %(message)s'
    logging.basicConfig(stream=sys.stderr, level=loglevel, format=FORMAT, datefmt='%m/%d/%Y %I:%M:%S %p')

    graph = pickle.load(open(args.explorationgraph, 'rb'))

    solve_timeouts = [0.13, 0.26, 0.52, 1.04, 2.08, 4.16, 8.32, 16.64, 33.28]

    root = graph.root_constraint
    worklist = PriorityQueue()  # (query_timeout: float, Constraint)
    workers = 7
    worker_pool = {i: None for i in range(1, workers + 1)}  # {(worker_id: int) : (finish_time: float)}
    worker_jobs = {i: None for i in range(1, workers + 1)}  # {(worker_id: int) : (Constraint, query_timeout: float)}
    exploration_timeout = 60
    time = 0
    solver_cpu = 0
    executed = set()  # {frozenset({((input_name: str), input_value)}}
    branches_covered = {} # {(source_file: str) : {(origin_line: int, dest_line: int)}}
    lines_covered = {} # {(source_file: str) : {line: int}}
    from symbolic.scheduling_policies import central_queue
    scheduler = central_queue

    # Initial worklist, take 0 time inputs (at least 1 will be the initial concrete values)
    for first_child in root.children:
        if first_child.solving_time == 0:
            worklist.put((solve_timeouts[0], first_child))

    logging.debug("Initial worklist size is {}".format(worklist.qsize()))

    while not worklist.empty() or any(finish_time is not None for finish_time in worker_pool.values()):

        if time > exploration_timeout:
            break

        for worker_id, finish_time in worker_pool.items():
            if finish_time is not None and finish_time <= time:
                constraint, query_timeout = worker_jobs[worker_id]
                worker_pool[worker_id] = None
                worker_jobs[worker_id] = None
                if query_timeout < constraint.solving_time:
                    # Query timed out
                    solver_cpu += query_timeout
                    timeout_index = solve_timeouts.index(query_timeout)
                    if timeout_index + 1 < len(solve_timeouts):
                        worklist.put((solve_timeouts[timeout_index + 1], constraint))
                else:
                    # Query finished
                    solver_cpu += constraint.solving_time
                    model = extract_model(constraint)
                    if model is not None:
                        executed.add(model)
                        collected_constraints = execute_model(constraint)
                        for collected_constraint in collected_constraints:
                            if extract_model(collected_constraint) not in executed:
                                worklist.put((solve_timeouts[0], collected_constraint))
                            else:
                                for file, branches in collected_constraint.branches_covered.items():
                                    if file in branches_covered:
                                        branches_covered[file] |= branches
                                    else:
                                        branches_covered[file] = set(branches)
                                for file, lines in collected_constraint.lines_covered.items():
                                    if file in lines_covered:
                                        lines_covered[file] |= lines
                                    else:
                                        lines_covered[file] = set(lines)

        for worker_id, finish_time in worker_pool.items():
            if finish_time is None:
                peeked = []
                selected_timeout, selected_constraint = None, None
                while not worklist.empty():
                    peeked_timeout, peeked_constraint = worklist.get()
                    candidate_worker = scheduler(worker_pool, solve_timeouts, peeked_timeout)
                    if candidate_worker is not None:
                        selected_timeout, selected_constraint = peeked_timeout, peeked_constraint
                        break
                    else:
                        peeked.append((peeked_timeout, peeked_constraint))
                for peeked_timeout, peeked_constraint in peeked:
                    worklist.put((peeked_timeout, peeked_constraint))

                if selected_constraint is None:
                    continue
                else:
                    if worker_pool[worker_id] is not None:
                        time_remaining = worker_pool[worker_id] - time
                        override_constraint, override_timeout = worker_jobs[worker_id]
                        time_spent = override_timeout - time_remaining
                        worklist.put((override_timeout, override_constraint))
                        solver_cpu += time_spent
                    worker_pool[worker_id] = selected_constraint.solving_time + time
                    worker_jobs[worker_id] = (selected_constraint, selected_timeout)

        upcoming_events = {event for event in worker_pool.values() if event is not None}
        if len(upcoming_events) > 0:
            time = min(upcoming_events)

    print("Execution time: {} seconds".format(time))
    print("Solver CPU: {} seconds".format(solver_cpu))
    print("Path coverage: {} paths".format(len(executed)))
    print("Line coverage: {} lines".format(sum(len(lines) for file, lines in lines_covered.items())))
    print("Branch coverage: {} branches".format(sum(len(branches) for file, branches in branches_covered.items())))


def execute_model(constraint):
    collected_constraints = [child for child in constraint.children]
    for child in constraint.children:
        if child.inputs == constraint.inputs:
            collected_constraints.extend(execute_model(child))
    return collected_constraints


def extract_model(constraint):
    if constraint is None or constraint.inputs is None:
        return None
    else:
        return frozenset((k, v) for k, v in constraint.inputs.items())


if __name__ == "__main__":
    main()
