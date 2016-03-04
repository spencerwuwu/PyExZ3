import sys
import logging
import time
import re
from tempfile import mkdtemp, NamedTemporaryFile
from subprocess import check_output, CalledProcessError

from CVC4 import ExprManager, SmtEngine, SExpr
from sexpdata import Symbol
import sexpdata

from .cvc_expr.exprbuilder import ExprBuilder
from .cvc_wrap import CVCWrapper

log = logging.getLogger("se.z3str2")
sys.setrecursionlimit(100000)

class Z3Str2Wrapper(object):
    options = {'produce-models': 'true',
               # Enable experimental string support
               'strings-exp': 'true',
               # Enable modular arithmetic with constant modulus
               'rewrite-divk': 'true',
               # Per Query timeout of 30 seconds
               'tlimit-per': 30000,
               'output-language': 'smt2',
               'input-language': 'smt2'}
    rename = {'str.len': 'Length',
              'str.contains': 'Contains',
              'str.indexof': 'Indexof2',
              'str.substr': 'Substring',
              'str.++': 'Concat',
              'str.replace': 'Replace',
              'str.at': 'CharAt',
              'bv2nat': 'bv2int'}
    logic = 'ALL_SUPPORTED'

    def __init__(self, query_store=None):
        if query_store is None:
            self.query_store = mkdtemp()
        else:
            self.query_store = query_store
        self.solvertime = 0

    def findCounterexample(self, asserts, query, timeout=10**10):
        starttime = time.process_time()
        Z3Str2Wrapper.options['tlimit-per'] = timeout * 1000
        self.solvetimeout = timeout
        self.em = ExprManager()
        self.solver = SmtEngine(self.em)
        for name, value in Z3Str2Wrapper.options.items():
            self.solver.setOption(name, SExpr(str(value)))
        self.solver.setLogic(Z3Str2Wrapper.logic)
        self.query = query
        self.asserts = asserts
        result, model = self._findModel()
        endtime = time.process_time()
        log.debug("Timeout -- %s" % timeout)
        log.debug("Result -- %s" % result)
        log.debug("Model -- %s" % model)
        log.debug("Solver time: {0:.2f} seconds".format(timeout))
        solvertime = endtime - starttime
        return result, model, solvertime

    def _findModel(self):
        self.solver.push()
        exprbuilder = ExprBuilder(self.asserts, self.query, self.solver)
        self.solver.assertFormula(exprbuilder.query.cvc_expr)
        smtlib = CVCWrapper._serialize(exprbuilder.query, exprbuilder.cvc_vars)
        transformed_smtlib = [self._transform(s) for s in sexpdata.parse(smtlib)]
        z3str2 = ""
        for line in transformed_smtlib:
            z3str2 += sexpdata.dumps(line, none_as='').strip().replace('\\\\', '\\') + "\n"
        rawoutput = None
        with NamedTemporaryFile(mode='w', suffix=".smt2") as f:
            f.write(z3str2)
            f.flush()
            startime = time.clock()
            try :
                rawoutput = str(check_output(["timeout", str(self.solvetimeout), "z3-str", "-f", f.name], universal_newlines=True))
            except CalledProcessError as e:
                if e.returncode == 124:
                    return "UNKNOWN", None
            endtime = time.clock()
            log.debug("Solver time: {0:.2f} seconds".format(endtime - startime))
            self.solvertime += endtime - startime
        if ">> SAT" not in rawoutput:
            return "UNSAT", None
        model = {}
        for name in exprbuilder.cvc_vars:
            patterns = {"{} : int -> (-?\d+)": int,
                        "{} : string -> \"([\S \\\\]*)\"": str}
            for pattern, constructor in patterns.items():
                match = re.search(pattern.format(name), rawoutput)
                if match is not None:
                    if constructor == str:
                        model[name] = bytes(constructor(match.group(1)), "utf-8").decode("unicode_escape")
                    else:
                        model[name] = constructor(match.group(1))
        return "SAT", model

    def _transform(self, smtlib):
        if isinstance(smtlib, Symbol) or isinstance(smtlib, int):
            return smtlib
        elif isinstance(smtlib, str):
            smtlib = smtlib.replace('\\', '\\\\')
            smtlib = smtlib.replace('\\\\v', '\\v')
            smtlib = smtlib.replace('\\\\x', '\\x')
            return smtlib
        if isinstance(smtlib[0], list):
            return [self._transform(subsmtlib) for subsmtlib in smtlib]
        stmtname = smtlib[0].value()
        if stmtname in ('set-logic', 'set-option'):
            return None
        elif stmtname == 'get-value':
            return Symbol('get-model'),
        elif stmtname == 'declare-fun':
            declare, name, func, smttype = smtlib
            return Symbol('declare-variable'), name, smttype
        elif stmtname == 'str.prefixof':
            stmtname, prefix, string = smtlib
            return Symbol('StartsWith'), self._transform(string), self._transform(prefix)
        elif stmtname in Z3Str2Wrapper.rename:
            return [Symbol(Z3Str2Wrapper.rename[stmtname])] + [self._transform(subsmtlib) for subsmtlib in smtlib[1:]]
        elif len(smtlib) > 1:
            return [smtlib[0]] + [self._transform(subsmtlib) for subsmtlib in smtlib[1:]]
        return smtlib


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