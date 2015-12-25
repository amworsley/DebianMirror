#! /usr/bin/python3

"""
# Test RepositoryMirror default constructor
>>> import RepositoryMirror
>>> a = RepositoryMirror.RepositoryMirror()
>>> a
RepositoryMirror(repo='http://web/security.debian.org', dists=['wheezy/updates', 'squeeze/updates', 'jessie/updates'], comps=['main', 'contrib', 'non-free'], archs=['amd64', 'all'], lmirror='security.debian.org')
>>> print(a)
Configuration file: RM.cfg
Repository: http://web/security.debian.org
distributions: ['wheezy/updates', 'squeeze/updates', 'jessie/updates']
components: ['main', 'contrib', 'non-free']
architectures: ['amd64', 'all']
Local Mirror stored in : security.debian.org
<BLANKLINE>
>>> a.getReleaseURL()
'http://web/security.debian.org/dists/wheezy/updates/Release'
>>> a.getReleasePath()
'security.debian.org/dists/wheezy/updates/Release'
>>> a.getReleaseURL()
'http://web/security.debian.org/dists/wheezy/updates/Release'

# Test Release File
>>> relfile = RepositoryMirror.RelFile(a, "wheezy", "test/dmirror/dists/wheezy/Release", None)
>>> relfile
RelFile(RepositoryMirror(repo='http://web/security.debian.org', dists=['wheezy/updates', 'squeeze/updates', 'jessie/updates'], comps=['main', 'contrib', 'non-free'], archs=['amd64', 'all'], lmirror='security.debian.org'), 'wheezy', 'test/dmirror/dists/wheezy/Release', None)
>>> print(relfile)
RelFile()
 name: wheezy
 file: test/dmirror/dists/wheezy/Release
 Suite: stable
 Codename: wheezy
 Version: 7.0
 Date: Sun, 10 Nov 2013 18:31:29 UTC
 Components: ['updates/main', 'updates/contrib', 'updates/non-free']
 Architectures: ['amd64', 'armel', 'armhf', 'i386', 'ia64', 'kfreebsd-amd64', 'kfreebsd-i386', 'mips', 'mipsel', 'powerpc', 's390', 's390x', 'sparc']
 Description: Debian 7.0 Security Updates

# Test checkFile() utility
>>> RepositoryMirror.checkFile('jessie-test/jessie-mirror/dists/jessie/contrib/binary-all/Packages.gz', size=0)
False
>>> RepositoryMirror.checkFile('jessie-test/jessie-mirror/dists/jessie/contrib/binary-all/Packages.gz', size=27049)
True
>>> RepositoryMirror.checkFile('jessie-test/jessie-mirror/dists/jessie/contrib/binary-all/Packages.gz', md5sum='abc')
checkFile(md5sum=abc) != bab1e8d873b38828727f399b90733654 - jessie-test/jessie-mirror/dists/jessie/contrib/binary-all/Packages.gz
False
>>> RepositoryMirror.checkFile('jessie-test/jessie-mirror/dists/jessie/contrib/binary-all/Packages.gz', md5sum='bab1e8d873b38828727f399b90733654')
True
>>> j = RepositoryMirror.RepositoryMirror(repo='jessie-test',dists=['jessie'],lmirror='tmp/jessie-mirror')
>>> j
RepositoryMirror(repo='jessie-test', dists=['jessie'], comps=['main', 'contrib', 'non-free'], archs=['amd64', 'all'], lmirror='tmp/jessie-mirror')
"""

import RepositoryMirror

if __name__ == "__main__":
    import doctest

    doctest.testmod()

