import logging
import time
import pickle
from os import path
from hashlib import sha224
from string import Template

from CVC4 import ExprManager, SmtEngine, SExpr

from symbolic.cvc_expr.exprbuilder import ExprBuilder

from symbolic.cvc_expr.integer import CVCInteger
from symbolic.cvc_expr.string import CVCString

log = logging.getLogger("se.cvc")


class CVCWrapper(object):
    options = {'produce-models': 'true',
               # Enable experimental string support
               'strings-exp': 'true',
               # Enable modular arithmetic with constant modulus
               'rewrite-divk': 'true',
               'output-language': 'smt2',
               'input-language': 'smt2'}
    logic = 'ALL_SUPPORTED'

    def __init__(self, query_store=None):
        self.asserts = None
        self.query = None
        self.em = None
        self.solver = None
        self.query_store = query_store
        self.smtlib = None

    def findCounterexample(self, asserts, query, timeout=None):
        """Tries to find a counterexample to the query while
           asserts remains valid."""
        startime = time.process_time()
        self.em = ExprManager()
        self.solver = SmtEngine(self.em)
        if timeout is not None:
            self.options['tlimit-per'] = timeout*1000
        for name, value in CVCWrapper.options.items():
            self.solver.setOption(name, SExpr(str(value)))
        self.solver.setLogic(CVCWrapper.logic)
        self.query = query
        self.asserts = asserts
        result, model = self._findModel()
        endtime = time.process_time()
        log.debug("Timeout -- %s" % timeout)
        log.debug("Result -- %s" % result)
        log.debug("Model -- %s" % model)
        log.debug("Solver time: {0:.2f} seconds".format(endtime - startime))
        solvertime = endtime - startime
        return result, model, solvertime

    def _findModel(self):
        self.solver.push()
        exprbuilder = ExprBuilder(self.asserts, self.query, self.solver)
        print("PRINT: START")
        for (name, cvc_var) in exprbuilder.cvc_vars.items():
            if isinstance(cvc_var, CVCString):
                print("PRINT: (declare-fun " + name + " () String)")
            elif isinstance(cvc_var, CVCInteger):
                print("PRINT: (declare-fun " + name + " () Int)")
        print("PRINT: (assert " + exprbuilder.query.cvc_expr.toString() + " )")
        print("PRINT: (check-sat)")
        print("PRINT: END")
        self.solver.assertFormula(exprbuilder.query.cvc_expr)
        if self.query_store is not None:
            self.smtlib = self._serialize(exprbuilder.query, exprbuilder.cvc_vars)
            self._savequery()
        model = None
        try:
            result = self.solver.checkSat()
            if not result.isSat():
                ret = "UNSAT"
            elif result.isUnknown():
                ret = "UNKNOWN"
            elif result.isSat():
                ret = "SAT"
                model = self._getModel(exprbuilder.cvc_vars)
            else:
                raise Exception("Unexpected SMT result")
        except RuntimeError as r:
            log.debug("CVC exception %s" % r)
            ret = "UNKNOWN"
        except TypeError as t:
            log.error("CVC exception %s" % t)
            ret = "UNKNOWN"
        self.solver.pop()
        return ret, model

    def _savequery(self):
        if not path.isdir(self.query_store):
            raise IOError("Query folder {} not found".format(self.query_store))
        smthash = sha224(bytes(str(self.query), 'UTF-8')).hexdigest()
        filename = path.join(self.query_store, "{}.smt2".format(smthash))
        log.debug('Writing query to {}'.format(filename))
        with open(filename, 'w') as f:
            f.write(self.smtlib)

    @staticmethod
    def _serialize(query, variables):
        smtlib_template = Template("""
(set-logic $logic)
(set-option :strings-exp ${strings_exp})
(set-option :produce-models ${produce_models})
(set-option :rewrite-divk ${rewrite_divk})

$declarevars

(assert $query)

(check-sat)

$getvars
""")
        assignments = {name.replace('-', '_'): value for name, value in CVCWrapper.options.items()}
        assignments['logic'] = CVCWrapper.logic
        assignments['query'] = query
        assignments['declarevars'] = "\n".join(
            "(declare-fun {} () {})".format(name, var.CVC_TYPE) for name, var in variables.items())
        assignments['getvars'] = "\n".join("(get-value ({}))".format(name) for name in variables)
        return smtlib_template.substitute(assignments).strip()

    @staticmethod
    def _getModel(variables):
        """Retrieve the model generated for the path expression."""
        return {name: cvc_var.getvalue() for (name, cvc_var) in variables.items()}
