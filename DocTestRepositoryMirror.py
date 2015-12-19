#! /usr/bin/python3

"""
>>> import RepositoryMirror
>>> a = RepositoryMirror.RepositoryMirror()
>>> a.repository
'http://web/security.debian.org'
>>> a.distributions
'wheezy/updates squeeze/updates jessie/updates'
>>> a.lmirror
'security.debian.org'
>>> a.dump_info()
Configuration file:  RM.cfg
Repository:  http://web/security.debian.org
distributions:  wheezy/updates squeeze/updates jessie/updates
components:  main contrib non-free
architectures:  amd64 all
Local Mirror stored in :  security.debian.org

"""

import RepositoryMirror

if __name__ == "__main__":
    import doctest

    doctest.testmod()

