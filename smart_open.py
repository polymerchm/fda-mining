import contextlib
import sys

@contextlib.contextmanager
def smart_open(filename=None, append=None, buffering=2):
    if filename and filename != '-':
        mode = 'a' if append else 'w'
        fh = open(filename, mode, buffering) # unbuffered
    else: 
        fh = sys.stdout
    try:
        yield fh
    finally:
        if fh is not sys.stdout:
            fh.close()
            
            