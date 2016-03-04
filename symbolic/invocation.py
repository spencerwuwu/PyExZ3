# Copyright: see copyright.txt

import logging

log = logging.getLogger("se.invocation")

class FunctionInvocation:
    def __init__(self, function, name, reset):
        self.function = function
        self.name = name
        self.reset = reset
        self.arg_constructor = {}
        self.initial_value = {}
        self.policy = lambda _ : True
        self.precondition = lambda _ : True

    def callFunction(self,args):
        self.reset()
        if not any(self.precondition(arg) for arg in args.values()):
            logging.info("Precondition Violation")
            return False
        result = self.function(**args)
        if not self.policy(result):
            print("Policy Violation")
            logging.info("Policy Violation")
        return result

    def addPolicy(self, policy):
        self.policy = policy

    def addPrecondition(self, precondition):
        self.precondition = precondition

    def getNames(self):
        return self.arg_constructor.keys()

    def addArgumentConstructor(self, name, init, constructor):
        self.initial_value[name] = init
        self.arg_constructor[name] = constructor

    def getNames(self):
        return self.arg_constructor.keys()

    def createArgumentValue(self, name, val=None):
        if val is None:
            val = self.initial_value[name]
        return self.arg_constructor[name](name, val)
