def symbolic(**arg_types):
    def decorator(f):
        f.symbolic_args = arg_types
        return f

    return decorator


def concrete(**arg_types):
    def decorator(f):
        f.concrete_args = arg_types
        return f

    return decorator


def policy(p):
    def decorator(f):
        f.policy = p
        return f

    return decorator


def precondition(p):
    def decorator(f):
        f.precondition = p
        return f

    return decorator
