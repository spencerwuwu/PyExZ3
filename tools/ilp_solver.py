__author__ = "Peter Chapman"

import sys
import logging
import pickle
import argparse

from cvxpy import Int, Maximize, Problem, sum_entries

def all_path_constraints(root_constraint):
    yield root_constraint
    constraints = list(root_constraint.children)
    while len(constraints) > 0:
        constraint = constraints.pop()
        constraints.extend(constraint.children)
        if constraint.inputs is not None:
            yield constraint

def extract_model(constraint):
    if constraint is None or constraint.inputs is None:
        return None
    else:
        return frozenset((k, v) for k, v in constraint.inputs.items())

def main():
    argparser = argparse.ArgumentParser(description="Solves for the optimal set of queries to attempt in order to "
                                                    "maximize coverage during a symbolic execution.")
    argparser.add_argument('explorationgraph', help="The serialized exploration graph on which to solve the best "
                                                    "scheduling strategy.")
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

    root = graph.root_constraint

    exploration_timeout = 0.1
    maximize_code = True
    maximize_branch = False
    assert(maximize_code != maximize_branch)


    ilp_constraints = []

    # Create constraint variables
    path_constraints = {} # {Constraint.id : ilp_constraint_id}
    for path_constraint in all_path_constraints(root):
        path_constraints[path_constraint.id] = len(path_constraints)
    ilp_path_constraints = Int(len(path_constraints))
    for ilp_path_constraint in ilp_path_constraints:
        ilp_constraints.append(ilp_path_constraint <= 1)
        ilp_constraints.append(ilp_path_constraint >= 0)

    # Create branch coverage variables
    if maximize_branch:
        branch_coverage = {} # {(filename, arc_origin, arc_dest) : ilp_branch_id}
        for path_constraint in all_path_constraints(root):
            for filename, arcs in path_constraint.branches_covered.items():
                for arc in arcs:
                    arc_origin, arc_dest = arc
                    if (filename, arc_origin, arc_dest) not in branch_coverage:
                        branch_coverage[(filename, arc_origin, arc_dest)] = len(branch_coverage)
        ilp_branches = Int(len(branch_coverage))
        for ilp_branch in ilp_branches:
            ilp_constraints.append(ilp_branch <= 1)
            ilp_constraints.append(ilp_branch >= 0)

    # Create code coverage variables
    if maximize_code:
        code_coverage = {} # {(filename, line): ilp_code_id}
        for path_constraint in all_path_constraints(root):
            for filename, lines in path_constraint.lines_covered.items():
                for line in lines:
                    if (filename, line) not in code_coverage:
                        code_coverage[(filename, line)] = len(code_coverage)
        ilp_code_lines = Int(len(code_coverage))
        for ilp_code_line in ilp_code_lines:
            ilp_constraints.append(ilp_code_line <= 1)
            ilp_constraints.append(ilp_code_line >= 0)

    # Calculate response times
    response_times = {} # {Constraint.id : response_time}
    for path_constraint in all_path_constraints(root):
        if path_constraint.parent is not None and path_constraint.parent.inputs == path_constraint.inputs:
            response_times[path_constraint.id] = 0.
        else:
            response_times[path_constraint.id] = path_constraint.solving_time

    # Constraint 1: Total solve time
    total_solve_time = 0
    for path_constraint_id, ilp_path_constraint_id in path_constraints.items():
        total_solve_time += ilp_path_constraints[ilp_path_constraint_id]*response_times[path_constraint_id]
    ilp_constraints.append(total_solve_time <= exploration_timeout)

    # Constraint 2: Seed input
    ilp_constraints.append(ilp_path_constraints[0] == 1)

    # Constraint 3: Branch discovery
    for path_constraint in all_path_constraints(root):
        parent = path_constraint.parent
        if parent is not None:
            # The constraint is only in the schedule if its parent is in the schedule
            ilp_constraints.append(ilp_path_constraints[path_constraints[path_constraint.id]] <= ilp_path_constraints[path_constraints[parent.id]])
            if extract_model(parent) == extract_model(path_constraint):
                ilp_constraints.append(ilp_path_constraints[path_constraints[path_constraint.id]] == ilp_path_constraints[path_constraints[parent.id]])

    # Constraint 4: Coverage
    ## A path constraint is "covering" a branch if the input that discovers the path constraint covers the branch.
    if maximize_branch:
        for branch, ilp_branch_var in branch_coverage.items():
            covering_path_constraints = 0
            for path_constraint in all_path_constraints(root):
                filename, arc_origin, arc_dest = branch
                if (arc_origin, arc_dest) in path_constraint.branches_covered.get(filename, set()):
                    covering_path_constraints += ilp_path_constraints[path_constraints[path_constraint.id]]
            assert(type(covering_path_constraints) != int)
            ilp_constraints.append(ilp_branches[ilp_branch_var] <= covering_path_constraints)

    if maximize_code:
        for code_line, ilp_code_line_var in code_coverage.items():
            covering_path_constraints = 0
            for path_constraint in all_path_constraints(root):
                filename, line = code_line
                if line in path_constraint.lines_covered.get(filename, set()):
                    covering_path_constraints += ilp_path_constraints[path_constraints[path_constraint.id]]
            assert(type(covering_path_constraints) != int)
            ilp_constraints.append(ilp_code_lines[ilp_code_line_var] <= covering_path_constraints)

    if maximize_branch:
        objective = Maximize(sum_entries(ilp_branches)) # Maximize branch coverage
    if maximize_code:
        objective = Maximize(sum_entries(ilp_code_lines)) # Maximize code coverage
    problem = Problem(objective, ilp_constraints)

    problem.solve()

    # Correctness assertions
    ## All constraints are 0 or 1 indicator variables
    for ilp_path_constraint_var in path_constraints.values():
        assert(0 <= round(ilp_path_constraints[ilp_path_constraint_var].value) <= 1)

    ## All branch coverage variables are 0 or 1
    if maximize_branch:
        for ilp_branch_var in branch_coverage.values():
            assert(0 <= round(ilp_branches[ilp_branch_var].value) <= 1)

    ## All code coverage variables are 0 or 1
    if maximize_code:
        for ilp_code_line_var in code_coverage.values():
            assert(0 <= round(ilp_code_lines[ilp_code_line_var].value) <= 1)

    ## Initial values are in the schedule and they have a response time of 0
    assert(round(ilp_path_constraints[path_constraints[0]].value) == 1)
    assert(response_times[path_constraints[0]] == 0)

    ## Constraints are discovered if used
    for path_constraint_id, ilp_path_constraint_var in path_constraints.items():
        if round(ilp_path_constraints[ilp_path_constraint_var].value) == 1:
            for path_constraint in all_path_constraints(root):
                if path_constraint.id == path_constraint_id and path_constraint.parent is not None:
                    assert(round(ilp_path_constraints[path_constraints[path_constraint.parent.id]].value) == 1)

    ## If input is used in constraint, then all constraints from that input are used as well
    for path_constraint_id, ilp_path_constraint_var in path_constraints.items():
        if round(ilp_path_constraints[ilp_path_constraint_var].value) == 1:
            path_constraint_input = None
            for path_constraint in all_path_constraints(root):
                if path_constraint_id == path_constraint.id:
                    path_constraint_input = extract_model(path_constraint)
            assert(path_constraint_input is not None or path_constraint_id == 0)
            for path_constraint in all_path_constraints(root):
                if extract_model(path_constraint) == path_constraint_input:
                    assert(round(ilp_path_constraints[path_constraints[path_constraint.id]].value) == 1)

    ## Branch coverage comes from discovered constraints
    if maximize_branch:
        for branch, ilp_branch_var in branch_coverage.items():
            if round(ilp_branches[ilp_branch_var].value) == 1:
                filename, arc_origin, arc_dest = branch
                assert(any((arc_origin, arc_dest) in path_constraint.branches_covered.get(filename, set()) for path_constraint
                           in all_path_constraints(root) if round(ilp_path_constraints[path_constraints[path_constraint.id]].value) == 1))

    ## Code coverage comes from discovered constraints
    if maximize_code:
        for code_line, ilp_code_line_var in code_coverage.items():
            if round(ilp_code_lines[ilp_code_line_var].value) == 1:
                filename, line = code_line
                assert(any(line in path_constraint.lines_covered.get(filename, set()) for path_constraint
                           in all_path_constraints(root) if round(ilp_path_constraints[path_constraints[path_constraint.id]].value) == 1))

    optimal_constraint_ids = set() # {Constraint.id}
    optimal_inputs = {} # {inputs : solving_time}
    optimal_branches = {} # {(source_file: str) : {(origin_line: int, dest_line: int)}}
    optimal_lines = {} # {(source_file: str) : {line: int}}
    for path_constraint_id, var_index in path_constraints.items():
        if bool(round(ilp_path_constraints[var_index].value)):
            optimal_constraint_ids.add(path_constraint_id)

    for path_constraint in all_path_constraints(root):
        if path_constraint.id in optimal_constraint_ids and not extract_model(path_constraint) is None:
            optimal_inputs[extract_model(path_constraint)] = path_constraint.solving_time
            for file, branches in path_constraint.branches_covered.items():
                if file in optimal_branches:
                    optimal_branches[file] |= branches
                else:
                    optimal_branches[file] = set(branches)
            for file, lines in path_constraint.lines_covered.items():
                if file in optimal_lines:
                    optimal_lines[file] |= lines
                else:
                    optimal_lines[file] = set(lines)

    print("Solver CPU: {} seconds".format(sum(optimal_inputs.values())))
    print("Path coverage: {} paths".format(len(optimal_inputs)))
    print("Line coverage: {} lines".format(sum(len(lines) for file, lines in optimal_lines.items())))
    print("Branch coverage: {} branches".format(sum(len(branches) for file, branches in optimal_branches.items())))

if __name__ == "__main__":
    main()
