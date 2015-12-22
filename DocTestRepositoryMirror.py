#! /usr/bin/python3

"""
>>> import RepositoryMirror
>>> a = RepositoryMirror.RepositoryMirror()
>>> a.dump_info()
Configuration file:  RM.cfg
Repository:  http://web/security.debian.org
distributions:  ['wheezy/updates', 'squeeze/updates', 'jessie/updates']
components:  main contrib non-free
architectures:  amd64 all
Local Mirror stored in :  security.debian.org
>>> a.getReleaseURL()
'http://web/security.debian.org/dists/wheezy/updates/Release'
>>> a.getReleasePath()
'security.debian.org/dists/wheezy/updates/Release'
>>> a.getReleaseURL()
'http://web/security.debian.org/dists/wheezy/updates/Release'
"""

import RepositoryMirror

if __name__ == "__main__":
    import doctest

    doctest.testmod()

