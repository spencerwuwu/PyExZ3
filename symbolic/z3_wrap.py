# Copyright: see copyright.txt

import time
import logging

from z3 import *
from .z3_expr.integer import Z3Integer
from .z3_expr.bitvector import Z3BitVector

log = logging.getLogger("se.z3")


class Z3Wrapper(object):
    def __init__(self):
        self.N = 32
        self.asserts = None
        self.query = None
        self.use_lia = True
        self.z3_expr = None

    def findCounterexample(self, asserts, query, timeout=None):
        """Tries to find a counterexample to the query while
           asserts remains valid."""
        # The current wrapper for Z3 ignores solve timeouts
        starttime = time.process_time()
        self.solver = Solver()
        self.solver.set(timeout=int(timeout * 1000))
        self.query = query
        self.asserts = asserts
        res, model = self._findModel()
        endtime = time.process_time()
        solvertime = endtime - starttime
        log.debug("Timeout -- %s" % timeout)
        log.debug("Result -- %s" % res)
        log.debug("Model -- %s" % model)
        log.debug("Solver time: {0:.2f} seconds".format(solvertime))
        return res, model, solvertime

    # private

    def _findModel(self):
        # Try QF_LIA first (as it may fairly easily recognize unsat instances)
        model = None
        if self.use_lia:
            self.solver.push()
            self.z3_expr = Z3Integer()
            self.z3_expr.toZ3(self.solver,self.asserts,self.query)
            res = self.solver.check()
            #print(self.solver.assertions)
            self.solver.pop()
            if res == unsat:
                return "UNSAT", model

        # now, go for SAT with bounds
        self.N = 32
        self.bound = (1 << 4) - 1
        while self.N <= 64:
            self.solver.push()
            (ret, mismatch) = self._findModel2()
            if not mismatch:
                break
            self.solver.pop()
            self.N += 8
            if self.N <= 64:
                print("expanded bit width to " + str(self.N))
        # print("Assertions")
        # print(self.solver.assertions())
        try:
            if ret == unsat:
                res = "UNSAT"
            elif ret == unknown:
                res = "UNKNOWN"
            elif not mismatch:
                res = "SAT"
                model = self._getModel()
            else:
                res = "UNKNOWN"
        except Z3Exception:
            res = "UNKNOWN"
        if self.N <= 64:
            self.solver.pop()
        return res, model

    def _setAssertsQuery(self):
        self.z3_expr = Z3BitVector(self.N)
        self.z3_expr.toZ3(self.solver, self.asserts, self.query)

    def _findModel2(self):
        self._setAssertsQuery()
        int_vars = self.z3_expr.getIntVars()
        res = unsat
        while res == unsat and self.bound <= (1 << (self.N - 1)) - 1:
            self.solver.push()
            constraints = self._boundIntegers(int_vars, self.bound)
            self.solver.assert_exprs(constraints)
            res = self.solver.check()
            if res == unsat:
                self.bound = (self.bound << 1) + 1
                self.solver.pop()
        if res == sat:
            # Does concolic agree with Z3? If not, it may be due to overflow
            model = self._getModel()
            # print("Match?")
            # print(self.solver.assertions)
            self.solver.pop()
            mismatch = False
            for a in self.asserts:
                evaluation = self.z3_expr.predToZ3(a, self.solver, model)
                if not evaluation:
                    mismatch = True
                    break
            if not mismatch:
                mismatch = not (not self.z3_expr.predToZ3(self.query, self.solver, model))
            # print(mismatch)
            return res, mismatch
        elif res == unknown:
            self.solver.pop()
        return res, False

    def _getModel(self):
        res = {}
        model = self.solver.model()
        for name in self.z3_expr.z3_vars.keys():
            try:
                ce = model.eval(self.z3_expr.z3_vars[name])
                res[name] = ce.as_signed_long()
            except:
                pass
        return res

    def _boundIntegers(self, variables, val):
        bval = BitVecVal(val, self.N, self.solver.ctx)
        bval_neg = BitVecVal(-val - 1, self.N, self.solver.ctx)
        return And([v <= bval for v in variables] + [bval_neg <= v for v in variables])
