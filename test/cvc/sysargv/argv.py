#!/usr/bin/python3
# http://www.programcreek.com/python/example/3/sys.argv

import sys

def main():
    """
    Call start() after parsing sys.argv for arguments:
        [-input script_file] data_file
    """
    data_file = None
    script_file = None
    if sys.argv and len(sys.argv) > 1:
        if sys.argv[1] == "-input":
            try: script_file = sys.argv[2]
            except IndexError:
                print("You need to specify a blot script for the -input option.")
                return
            try: data_file = sys.argv[3]
            except IndexError:
                print("You need to specify a data filename.")
                return
        else: data_file = sys.argv[1]
    print(data_file, script_file)

if __name__ == "__main__":
   main()