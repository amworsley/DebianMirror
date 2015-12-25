#! /usr/bin/python3

"""
>>> import subprocess
>>> subprocess.call("/bin/rm -rf tmp", shell=True)
0
>>> subprocess.call("./test-jessie.sh", shell=True)
0
"""

import RepositoryMirror

if __name__ == "__main__":
    import doctest

    doctest.testmod()
