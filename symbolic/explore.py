# Copyright: see copyright.txt


import logging
import time
import traceback
from multiprocessing import Process, Queue
from operator import attrgetter
from os import path
from queue import PriorityQueue
from sys import exc_info, platform

import coverage

import symbolic.scheduling_policies
from .path_to_constraint import PathToConstraint
from .symbolic_types import symbolic_type, SymbolicType
from .z3_wrap import Z3Wrapper

log = logging.getLogger("se.conc")


class ExplorationEngine:
    DEFAULT_SOLVE_TIMEOUTS = [0.13, 0.26, 0.52, 1.04, 2.08, 4.16, 8.32, 16.64, 33.28]
    SLEEP_WAIT = 0.02

    def __init__(self, funcinv, solver="z3", query_store=None, solvetimeouts=None, pathtimeout=None,
                 coverage_pruning=None, workers=1, scheduling_policy="central_queue"):
        self.invocation = funcinv
        # the input to the function
        self.symbolic_inputs = {}  # string -> SymbolicType
        self.one_execution_coverage = coverage.CoverageData()
        self.global_execution_coverage = coverage.CoverageData()
        # initialize
        for n in funcinv.getNames():
            self.symbolic_inputs[n] = funcinv.createArgumentValue(n)
        self.constraints_to_solve = PriorityQueue()
        self.new_constraints = []
        self.num_processed_constraints = 0
        self.path = PathToConstraint(lambda c: self.addConstraint(c), funcinv.name)
        # link up SymbolicObject to PathToConstraint in order to intercept control-flow
        symbolic_type.SymbolicObject.SI = self.path

        if solvetimeouts is None:
            solvetimeouts = ExplorationEngine.DEFAULT_SOLVE_TIMEOUTS
        self.solvetimeouts = sorted(set(solvetimeouts))
        self.pathtimeout = pathtimeout
        self.coverage_pruning = coverage_pruning

        self.solver = solver
        self.total_solve_time = 0
        self.last_solve_time = 0

        self.worker_pool = {i: None for i in range(1, workers + 1)}
        self.worker_jobs = {i: None for i in range(1, workers + 1)}
        log.info("Using {} solver workers".format(len(self.worker_pool)))
        self.finished_queries = Queue()

        self.scheduling_policy = attrgetter(scheduling_policy)(symbolic.scheduling_policies)

        self.query_store = query_store
        if self.query_store is not None:
            if not path.isdir(self.query_store):
                raise IOError("Query folder {} not found".format(self.query_store))

        # outputs
        self.solved_constraints = set()
        self.outstanding_constraint_attempts = {}
        self.generated_inputs = []
        self.execution_return_values = []

    def addConstraint(self, constraint):
        self.new_constraints.append(constraint)

    def pruned(self, constraint):
        current_path_time = 0
        path_inputs = set()
        c = constraint
        while c is not None:
            if self.frozen_model(c.inputs) not in path_inputs:
                current_path_time += c.solving_time
            frozen = self.frozen_model(c.inputs)
            path_inputs.add(frozen)
            c = c.parent
        log.debug("Path solve time {}".format(current_path_time))


        parent_code_coverage = set()  # {(filename, line)}
        parent_branch_coverage = set()  # {(filename, arc_origin, arc_dest)}
        parent_search_depth = self.coverage_pruning if self.coverage_pruning is not None else 0
        c = constraint
        while c is not None and parent_search_depth > 0:
            if c.parent is not None and c.inputs is not None and c.parent.inputs is not None and \
                            {name: value.getConcrValue() for name, value in c.inputs.items()} != \
                            {name: value.getConcrValue() for name, value in c.parent.inputs.items()}:
                parent_search_depth -= 1
                for filename, lines in c.parent.lines_covered.items():
                    for line in lines:
                        parent_code_coverage.add((filename, line))
                for filename, branches in c.parent.branches_covered.items():
                    for branch in branches:
                        arc_origin, arc_dest = branch
                        parent_branch_coverage.add((filename, arc_origin, arc_dest))
            c = c.parent
        node_code_coverage = set()
        node_branch_coverage = set()
        for filename, lines in constraint.lines_covered.items():
                for line in lines:
                        node_code_coverage.add((filename, line))
                for filename, branches in constraint.branches_covered.items():
                    for branch in branches:
                        arc_origin, arc_dest = branch
                        node_branch_coverage.add((filename, arc_origin, arc_dest))
        log.debug("Parent code coverage {}, {}".format(c.inputs if c is not None else c, sorted([line[1] for line in parent_code_coverage])))
        log.debug("Current code coverage {}, {}".format(constraint.inputs, sorted([line[1] for line in node_code_coverage])))
        log.debug("Parent branch coverage {}, {}".format(c.inputs if c is not None else c, sorted([branch[1:] for branch in parent_code_coverage])))
        log.debug("Current branch coverage {}, {}".format(constraint.inputs, sorted([branch[1:] for branch in node_code_coverage])))
        if (self.pathtimeout is None or current_path_time < self.pathtimeout) and \
                (self.coverage_pruning is None or
                         parent_search_depth != 0 or (len(parent_code_coverage) + len(parent_branch_coverage) == 0)
                 or not (parent_code_coverage >= node_code_coverage)
                 or not (parent_branch_coverage >= node_branch_coverage)):
            return False
        else:
            log.debug("Pruned {}".format(constraint))
            return True

    def explore(self, max_iterations=0, timeout=None):
        self._oneExecution()
        starttime = time.time()
        iterations = 1
        try:
            while not self._isExplorationComplete():

                if max_iterations != 0 and iterations >= max_iterations:
                    log.info("Maximum number of iterations reached, terminating")
                    break

                if timeout is not None and (time.time() - starttime) > timeout:
                    log.info("Timeout reached, terminating")
                    break

                # Check for finished queries
                if not self.finished_queries.empty():
                    log.debug("Processing finished query")
                    ## Select finished query
                    selected_id, selected_timeout, result, model, solving_time = self.finished_queries.get_nowait()
                    if selected_id in self.solved_constraints:
                        continue
                    selected = self.path.find_constraint(selected_id) # symbolic.constraint.Constraint
                elif self.constraints_to_solve.empty() or self._runningSolvers() == len(self.worker_pool):
                    log.debug("Waiting for solvers to finish")
                    ## Wait for running queries to finish
                    self._wait()
                    continue
                else:
                    ## Find constraint with free worker
                    peeked = []
                    selected_timeout, selected = None, None
                    while not self.constraints_to_solve.empty():
                        peeked_timeout, peeked_constraint = self.constraints_to_solve.get()
                        candidate_worker = self.scheduling_policy(self.worker_pool, self.solvetimeouts, peeked_timeout)
                        if candidate_worker is not None:
                            selected_timeout, selected = peeked_timeout, peeked_constraint
                            break
                        else:
                            peeked.append((peeked_timeout, peeked_constraint))

                    for peeked_timeout, peeked_constraint in peeked:
                        self.constraints_to_solve.put((peeked_timeout, peeked_constraint))

                    if selected is None:
                        self._wait()
                        continue

                    if selected.processed:
                        continue

                    if self.pruned(selected):
                        continue

                    self._launch_worker(selected.id, selected_timeout, selected, self.solver)
                    continue

                self.last_solve_time = solving_time
                self.total_solve_time += self.last_solve_time

                # Tracking multiple attempts of the same query with different solvers
                self.outstanding_constraint_attempts[(selected.id, selected_timeout)] -= 1

                if selected.id in self.solved_constraints:
                    continue

                if selected.branch_id is not None:
                    log.info("\t".join(["Solver Result", selected.branch_id, result]))

                if model is None:
                    if self._running_constraint(selected.id) is not None or self.outstanding_constraint_attempts[(selected.id, selected_timeout)] > 0:
                        continue
                    timeout_index = self.solvetimeouts.index(selected_timeout)
                    if timeout_index + 1 < len(self.solvetimeouts) and result != "UNSAT":
                            selected.processed = False
                            self.constraints_to_solve.put((self.solvetimeouts[timeout_index + 1], selected))
                    else:
                            from symbolic.predicate import Predicate
                            negated_predicate = Predicate(selected.predicate.symtype, not selected.predicate.result)
                            added_constraint = selected.parent.addChild(negated_predicate)
                            added_constraint.input = None
                            added_constraint.solving_time = solving_time
                    continue
                else:
                    while self._running_constraint(selected.id) is not None:
                        worker_id = self._running_constraint(selected.id)
                        if worker_id is None:
                            continue
                        worker = self.worker_pool[worker_id]
                        worker.terminate()
                        self.worker_pool[worker_id] = None
                        self.worker_jobs[worker_id] = None

                    for name in model.keys():
                        self._updateSymbolicParameter(name, model[name])

                self._oneExecution(selected)

                iterations += 1
                self.num_processed_constraints += 1
                self.solved_constraints.add(selected.id)

        finally:
            for worker_id, worker in self.worker_pool.items():
                if worker is not None:
                    worker.terminate()

        return self.generated_inputs, self.execution_return_values, self.path

    def _running_constraint(self, constraint_id):
        for worker_id, job_info in self.worker_jobs.items():
            if job_info is None:
                continue
            timeout, constraint = job_info
            if constraint_id == constraint.id:
                return worker_id
        return None

    def _wait(self):
        while self.finished_queries.empty() and self._runningSolvers() > 0:
            time.sleep(ExplorationEngine.SLEEP_WAIT)
            for worker_id, worker in self.worker_pool.items():
                if worker is not None:
                    worker.join(ExplorationEngine.SLEEP_WAIT)

    # private

    def _runningSolvers(self):
        for worker_id, worker in self.worker_pool.items():
            if worker is not None and not worker.is_alive():
                worker.terminate()
                self.worker_pool[worker_id] = None
                self.worker_jobs[worker_id] = None
        return sum(1 if solver_worker is not None else 0 for solver_worker in self.worker_pool.values())

    def _launch_worker(self, selected_id, selected_timeout, selected_constraint, solver):
        if solver not in {'z3', 'cvc', 'z3str2', 'multi'}:
            raise Exception("Unknown solver %s" % solver)

        if solver == 'multi':
            primary, secondary = ('cvc', 'z3str2') if any(isinstance(input, str) for input in self.symbolic_inputs.values()) else ('z3', 'cvc')
            self._launch_worker(selected_id, selected_timeout, selected_constraint, primary)
            while self._runningSolvers() == len(self.worker_pool):
                log.debug("Waiting for spot for second solver")
                self._wait()
            self._launch_worker(selected_id, selected_timeout, selected_constraint, secondary)
            return

        self.outstanding_constraint_attempts[(selected_id, selected_timeout)] = self.outstanding_constraint_attempts.get((selected_id, selected_timeout), 0) + 1

        worker_id = self.scheduling_policy(self.worker_pool, self.solvetimeouts, selected_timeout)
        if self.worker_pool[worker_id] is not None:
            running_timeout, running_constraint = self.worker_jobs[worker_id]
            self.constraints_to_solve.put((running_timeout, running_constraint))
            self.worker_pool[worker_id].terminate()
            self.worker_pool[worker_id] = None
            self.worker_jobs[worker_id] = None

        asserts, query = selected_constraint.getAssertsAndQuery()
        p = Process(target=self._solve, args=(
            self.finished_queries, solver, selected_id, selected_timeout, asserts, query, self.query_store))
        self.worker_pool[worker_id] = p
        self.worker_jobs[worker_id] = selected_timeout, selected_constraint
        p.start()

    @staticmethod
    def _solve(finished_queries, solver_type, selected_id, selected_timeout, asserts, query, query_store):
        if solver_type == 'z3':
            solver_instance = Z3Wrapper()
        elif solver_type == 'cvc':
            from .cvc_wrap import CVCWrapper
            solver_instance = CVCWrapper(query_store=query_store)
        elif solver_type == "z3str2":
            from .z3str2_wrap import Z3Str2Wrapper
            solver_instance = Z3Str2Wrapper(query_store=query_store)
        result, model, solving_time = solver_instance.findCounterexample(asserts, query, timeout=selected_timeout)
        finished_queries.put((selected_id, selected_timeout, result, model, solving_time))

    def _updateSymbolicParameter(self, name, val):
        self.symbolic_inputs[name] = self.invocation.createArgumentValue(name, val)

    def _getInputs(self):
        return self.symbolic_inputs.copy()

    def _setInputs(self, d):
        self.symbolic_inputs = d

    def _isExplorationComplete(self):
        num_constr = self.constraints_to_solve.qsize()
        if num_constr == 0 and self._runningSolvers() == 0 and self.finished_queries.empty():
            log.info("Exploration complete")
            return True
        else:
            constraints_to_solve = num_constr + self._runningSolvers()
            try:
                pending_process = self.finished_queries.qsize()
            except NotImplementedError:
                assert platform == 'darwin'  #only allow this hack on OS X
                pending_process = 0
            processed_constraints = self.num_processed_constraints
            log.info("%d constraints yet to solve (total: %d, already solved: %d)" % (
                constraints_to_solve, constraints_to_solve + pending_process + processed_constraints,
                processed_constraints))
            return False

    def _getConcrValue(self, v):
        if isinstance(v, SymbolicType):
            return v.getConcrValue()
        else:
            return v

    def _recordInputs(self):
        args = self.symbolic_inputs
        inputs = [(k, self._getConcrValue(args[k])) for k in args]
        self.generated_inputs.append(inputs)
        print(inputs)

    def _oneExecution(self, expected_path=None):
        self._recordInputs()
        self.path.reset(expected_path)
        try:
            cov = coverage.Coverage(omit=["*pyexz3.py", "*symbolic*", "*pydev*", "*coverage*"], branch=True)
            cov.start()
            ret = self.invocation.callFunction(self.symbolic_inputs)
            cov.stop()
            self.one_execution_coverage = cov.get_data()
            self.global_execution_coverage.update(self.one_execution_coverage)
            total_lines, executed_lines, executed_branches = self.coverage_statistics()
            log.info("Line coverage {}/{} ({:.2%})".format(executed_lines, total_lines, (executed_lines/total_lines) if total_lines > 0 else 0))
            log.info("Branch coverage {}".format(executed_branches))

            while len(self.new_constraints) > 0:
                constraint = self.new_constraints.pop()
                constraint.inputs = self._getInputs()
                constraint.set_coverage(self.one_execution_coverage)
                constraint.solving_time = self.last_solve_time
                self.constraints_to_solve.put((self.solvetimeouts[0], constraint))

        except Exception as e:
            print("Exception")
            instrumentation_keywords = {"pyexz3.py", "symbolic", "pydev", "coverage"}
            exc_type, exc_value, exc_traceback = exc_info()
            for filename, line, function, text in reversed(traceback.extract_tb(exc_traceback)):
                if any(instrumentation_keyword in filename for instrumentation_keyword in instrumentation_keywords):
                    continue
                else:
                    e.id = "{}:{}".format(filename, line)
                    print(e.id)
                    break
            ret = e
        print(ret)
        self.execution_return_values.append(ret)

    def coverage_statistics(self):
        cov = coverage.Coverage(omit=["*pyexz3.py", "*symbolic*", "*pydev*", "*coverage*"], branch=True)
        total_lines = 0
        executed_lines = 0
        executed_branches = 0
        for file in self.global_execution_coverage.measured_files():
            _, executable_lines, _, _ = cov.analysis(file)
            total_lines += len(set(executable_lines))
            executed_lines += len(set(self.global_execution_coverage.lines(file)))
            executed_branches += len(set(self.global_execution_coverage.arcs(file)))
        return total_lines, executed_lines, executed_branches


    def frozen_model(self, inputs):
        if inputs is None:
            return None
        else:
            return frozenset((k, v) for k, v in inputs.items())
