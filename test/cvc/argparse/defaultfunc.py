import argparse

def foo(args):
    if args.no_cache:
        print("verbosity turned on")

parser = argparse.ArgumentParser()
parser.add_argument("--no-cache", action="store_true")
parser.set_defaults(func=foo)
args = parser.parse_args()
args.func(args)


