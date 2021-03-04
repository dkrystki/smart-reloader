import pdb
import sys


debugger = pdb.Pdb()
debugger.set_trace()
debugger.set_break("sandbox.py", 14)


def fun():
    print("aha1")
    print(__file__)
    print("aha2")
    print("aha3")

fun()
