import logging
import time

from CVC4 import ExprManager, SmtEngine, SExpr

from symbolic.cvc_expr.exprbuilder import ExprBuilder

log = logging.getLogger("se.cvc")


class CVCWrapper(object):
    options = {'produce-models': 'true',
               # Enable experimental string support
               'strings-exp': 'true',
               # Enable modular arithmetic with constant modulus
               'rewrite-divk': 'true',
               # Per Query timeout of 30 seconds
               'tlimit-per': 30000,
               'output-language': 'smt2',
               'input-language': 'smt2'}
    logic = 'ALL_SUPPORTED'

    def __init__(self, solvetimeout=30):
        self.asserts = None
        self.query = None
        self.em = None
        self.solver = None
        self.solvertime = 0
        self.options['tlimit-per'] = solvetimeout * 1000

    def findCounterexample(self, asserts, query):
        """Tries to find a counterexample to the query while
           asserts remains valid."""
        self.em = ExprManager()
        self.solver = SmtEngine(self.em)
        for name, value in CVCWrapper.options.items():
            self.solver.setOption(name, SExpr(str(value)))
        self.solver.setLogic(CVCWrapper.logic)
        self.query = query
        self.asserts = self._coneOfInfluence(asserts, query)
        result = self._findModel()
        log.debug("Query -- %s" % self.query)
        log.debug("Asserts -- %s" % asserts)
        log.debug("Cone -- %s" % self.asserts)
        log.debug("Result -- %s" % result)
        return result

    def _findModel(self):
        self.solver.push()
        exprbuilder = ExprBuilder(self.asserts, self.query, self.solver)
        self.solver.assertFormula(exprbuilder.query.cvc_expr)
        try:
            startime = time.clock()
            result = self.solver.checkSat()
            endtime = time.clock()
            log.debug("Solver time: {0:.2f} seconds".format(endtime - startime))
            self.solvertime += endtime - startime
            if not result.isSat():
                ret = None
            elif result.isUnknown():
                ret = None
            elif result.isSat():
                ret = self._getModel(exprbuilder.cvc_vars)
            else:
                raise Exception("Unexpected SMT result")
        except RuntimeError as r:
            log.debug("CVC exception %s" % r)
            ret = None
        self.solver.pop()
        return ret

    @staticmethod
    def _getModel(variables):
        """Retrieve the model generated for the path expression."""
        return {name: cvc_var.getvalue() for (name, cvc_var) in variables.items()}

    @staticmethod
    def _coneOfInfluence(asserts, query):
        cone = []
        cone_vars = set(query.getVars())
        ws = [a for a in asserts if len(set(a.getVars()) & cone_vars) > 0]
        remaining = [a for a in asserts if a not in ws]
        while len(ws) > 0:
            a = ws.pop()
            a_vars = set(a.getVars())
            cone_vars = cone_vars.union(a_vars)
            cone.append(a)
            new_ws = [a for a in remaining if len(set(a.getVars()) & cone_vars) > 0]
            remaining = [a for a in remaining if a not in new_ws]
            ws = ws + new_ws
        return cone
