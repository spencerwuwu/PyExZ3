# Copyright: copyright.txt

from collections import namedtuple

import inspect
import logging
import os
import sys
import re
from importlib.machinery import SourceFileLoader

from symbolic.invocation import FunctionInvocation
from symbolic.symbolic_types import SymbolicType, SymbolicInteger, getSymbolic, SymbolicStr

# The built-in definition of len wraps the return value in an int() constructor, destroying any symbolic types.
# By redefining len here we can preserve symbolic integer types.
import builtins

builtins.len = (lambda x: x.__len__())
builtins.abs = (lambda x: x if x > 0 else x * -1)
builtins.hash = (lambda x: x.__hash__())

sys.old_exit = sys.exit


def new_exit(status_code):
    instrumentation_keywords = {"pyexz3.py", "symbolic", "multiprocessing"}
    frame, filename, linenum, funcname, context, contextline = inspect.stack().pop(1)
    if any(instrumentation_keyword in filename for instrumentation_keyword in instrumentation_keywords):
        sys.old_exit(status_code)
    else:
        raise Exception("Program Exit ({})".format(status_code))


sys.exit = new_exit

log = logging.getLogger("se.loader")


class Loader:
    def __init__(self, filename, entry):
        self.app = None

        self.modulename = os.path.basename(filename)
        self.modulename, ext = os.path.splitext(self.modulename)
        self.filename = filename

        if (entry == ""):
            self.entrypoint = self.modulename
        else:
            self.entrypoint = entry

        self._reset(True)

    def _reset(self, firstpass=False, modulename=None):
        if modulename is None:
            modulename = self.modulename
        if firstpass and modulename in sys.modules and modulename != "__main__":
            print("There already is a module loaded named " + modulename)
            raise ImportError()
        try:
            if modulename in sys.modules:
                del (sys.modules[modulename])
            self.app = SourceFileLoader(modulename, self.filename).load_module()
        except Exception as arg:
            print("Couldn't import " + modulename)
            print(arg)
            raise ImportError()

    def _initializeArgumentConcrete(self, inv: FunctionInvocation, f, val):
        inv.addArgumentConstructor(f, val, lambda n, v: val)

    def _initializeArgumentSymbolic(self, inv: FunctionInvocation, f: str, val, st: SymbolicType):
        inv.addArgumentConstructor(f, val, lambda n, v: st(n, v))

    def execution_complete(self, return_vals):
        print("{}.py execution complete.".format(self.modulename))


class MainLoader(Loader):
    def createInvocation(self):
        return FunctionInvocation(self._execute, "main", self._reset)

    def _execute(self, **kwargs):
        self.instrument(**kwargs)
        SourceFileLoader("__main__", self.filename).load_module()

    def instrument(self, **kwargs: {str: SymbolicStr}):
        raise NotImplementedError

    def _reset(self, firstpass=False, modulename="__main__"):
        if firstpass:
            try:
                super()._reset(firstpass, modulename)
            except ImportError as e:
                log.warn("Found error {} while recording argparse inputs".format(str(e)))
        elif modulename in sys.modules:
            del (sys.modules[modulename])


class SysArgvLoader(MainLoader):
    def createInvocation(self):
        inv = super().createInvocation()
        for index in range(10):
            self._initializeArgumentSymbolic(inv, "sys.argv[{}]".format(index), str(), getSymbolic(str()))
        return inv

    def instrument(self, **kwargs: {str: SymbolicStr}):
        indexregex = re.compile(r"[0-9]+")
        sys.argv = [value for value in kwargs.values()]
        for name, val in kwargs.items():
            index = int(indexregex.search(name).group())
            sys.argv[index] = val

class CLIParseLoader(MainLoader):
    def __init__(self, filename, entry):
        self.tracked_inputs = {}
        super(CLIParseLoader, self).__init__(filename, entry)

    def createInvocation(self):
        inv = FunctionInvocation(self._execute, "main", self._reset)
        for variable, type in self.tracked_inputs.items():
            self._initializeArgumentSymbolic(inv, variable, type(), getSymbolic(type()))
        return inv

    def record(self):
        raise NotImplementedError

    def _restore(self):
        raise NotImplementedError

    def _reset(self, firstpass=False, modulename="__main__"):
        self.record()
        super()._reset(firstpass, modulename)
        self._restore()

class OptParseLoader(CLIParseLoader):
    def __init__(self, filename, entry):
        import optparse
        self.optparse = optparse
        self.original_add_option = self.optparse.OptionParser.add_option
        self.original_parse_args = self.optparse.OptionParser.parse_args
        super(OptParseLoader, self).__init__(filename, entry)

    def record(self):
        def new_add_option(optparser_self, *args, **kwargs):
            if kwargs.get('action', ) != 'help':
                if 'dest' not in kwargs:
                    name = args[0].strip('-') if not len(args) > 1 else args[1].strip('-')
                    name = name.replace('-', '_')
                else:
                    name = kwargs['dest']
                self.tracked_inputs[name] = int
                log.info("Recorded symbolic input {} as type {}".format(name, self.tracked_inputs[name]))
            self.original_add_option(optparser_self, *args, **kwargs)

        def new_parse_args(optparser_self, args=None, namespace=None):
            log.debug('Recording argument parsing')
            return self.original_parse_args(optparser_self, [], None)

        self.optparse.OptionParser.add_option= new_add_option
        self.optparse.OptionParser.parse_args = new_parse_args

    def instrument(self, **kwargs):
        def new_parse_args(optparser, args=None, values=None):
            OptContainer = namedtuple('OptContainer', ' '.join(kwargs.keys()))
            options = OptContainer(**kwargs)
            return options, []

        self.optparse.OptionParser.parse_args = new_parse_args

    def _restore(self):
        self.optparse.OptionParser.add_option = self.original_add_option
        self.optparse.OptionParser.parse_args = self.original_parse_args

class ArgParseLoader(CLIParseLoader):
    def __init__(self, filename, entry):
        import argparse
        self.argparse = argparse
        self.original_add_argument = self.argparse.ArgumentParser.add_argument
        self.original_parse_args = self.argparse.ArgumentParser.parse_args

        self.default_func = None

        super(ArgParseLoader, self).__init__(filename, entry)

    def record(self):
        def new_add_argument(argumentparser_self, *args, **kwargs):
            if kwargs.get('action', ) != 'help':
                name = args[0].strip('-') if not len(args) > 1 else args[1].strip('-')
                name = name.replace('-', '_')
                self.tracked_inputs[name] = int
                log.info("Recorded symbolic input {} as type {}".format(name, self.tracked_inputs[name]))
            self.original_add_argument(argumentparser_self, *args, **kwargs)

        def new_set_defaults(argumentparser_self, *args, **kwargs):
            if 'func' in kwargs:
                self.default_func = kwargs['func']

        def new_parse_args(argumentparser_self, args=None, namespace=None):
            log.debug('Recording argument parsing')
            return self.original_parse_args(argumentparser_self, [], namespace)

        self.argparse.ArgumentParser.add_argument = new_add_argument
        self.argparse.ArgumentParser.parse_args = new_parse_args
        self.argparse.ArgumentParser.set_defaults = new_set_defaults

    def instrument(self, **kwargs):
        def new_parse_args(argumentparser_self, args=None, namespace=None):
            ArgContainer = namedtuple('ArgContainer', ' '.join(kwargs.keys()) + ' func')
            args = ArgContainer(func=self.default_func, **kwargs)
            return args

        self.argparse.ArgumentParser.parse_args = new_parse_args

    def _restore(self):
        self.argparse.ArgumentParser.add_argument = self.original_add_argument
        self.argparse.ArgumentParser.parse_args = self.original_parse_args


class FunctionLoader(Loader):
    def createInvocation(self):
        inv = FunctionInvocation(self._execute, self.entrypoint, self._reset)
        func = self.app.__dict__[self.entrypoint]
        argspec = inspect.getargspec(func)
        # check to see if user specified initial values of arguments
        if "concrete_args" in func.__dict__:
            for (f, v) in func.concrete_args.items():
                if not f in argspec.args:
                    print("Error in @concrete: " + self.entrypoint + " has no argument named " + f)
                    raise ImportError()
                else:
                    self._initializeArgumentConcrete(inv, f, v)
        if "symbolic_args" in func.__dict__:
            for (f, v) in func.symbolic_args.items():
                if not f in argspec.args:
                    print("Error (@symbolic): " + self.entrypoint + " has no argument named " + f)
                    raise ImportError()
                elif f in inv.getNames():
                    print("Argument " + f + " defined in both @concrete and @symbolic")
                    raise ImportError()
                else:
                    s = getSymbolic(v)
                    if (s == None):
                        print(
                            "Error at argument " + f + " of entry point " + self.entrypoint +
                            " : no corresponding symbolic type found for type " + str(type(v)))
                        raise ImportError()
                    self._initializeArgumentSymbolic(inv, f, v, s)
        for a in argspec.args:
            if not a in inv.getNames():
                self._initializeArgumentSymbolic(inv, a, 0, SymbolicInteger)
        if "policy" in func.__dict__:
            inv.addPolicy(func.policy)
        if "precondition" in func.__dict__:
            inv.addPrecondition(func.precondition)
        return inv

    def execution_complete(self, return_vals):
        if "expected_result" in self.app.__dict__:
            return self._check(return_vals, self.app.__dict__["expected_result"]())
        if "expected_result_set" in self.app.__dict__:
            return self._check(return_vals, self.app.__dict__["expected_result_set"](), False)
        else:
            print(self.modulename + ".py contains no expected_result function")
            return True

    def _toBag(self, l):
        bag = {}
        for i in l:
            if i in bag:
                bag[i] += 1
            else:
                bag[i] = 1
        return bag

    def _check(self, computed, expected, as_bag=True):
        b_c = self._toBag(computed)
        b_e = self._toBag(expected)
        if as_bag and b_c != b_e or not as_bag and set(computed) != set(expected):
            print("-------------------> %s test failed <---------------------" % self.modulename)
            print("Expected: %s, found: %s" % (b_e, b_c))
            return False
        else:
            print("%s test passed <---" % self.modulename)
            return True

    def _reset(self, firstpass=False, modulename=None):
        super()._reset(firstpass)
        if not self.entrypoint in self.app.__dict__ or not callable(self.app.__dict__[self.entrypoint]):
            print("File " + self.modulename + ".py doesn't contain a function named " + self.entrypoint)
            raise ImportError()

    def _execute(self, **kwargs):
        return self.app.__dict__[self.entrypoint](**kwargs)


def loaderFactory(filename, entry, loader=None):
    if not os.path.isfile(filename):
        print("Please provide a Python file to load")
        return None
    try:
        directory = os.path.dirname(filename)
        sys.path = [directory] + sys.path
        loader_map = {'argparse': ArgParseLoader, 'sysargv': SysArgvLoader, 'optparse': OptParseLoader}
        loader_class = loader_map.get(loader, FunctionLoader)
        ret = loader_class(filename, entry)
        return ret
    except ImportError:
        sys.path = sys.path[1:]
        return None
