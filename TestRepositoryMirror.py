#! /usr/bin/python3

import RepositoryMirror
import unittest

# dummy test repository
drep = 'file:///test/dmirror'
ddists = 'wheezy'.split()
dcomp = 'main contrib'.split()
darch = 'amd64'.split()
dmirror = 'test/tmp-mirror'


class TestRelFile(unittest.TestCase):
    ''' Read in a Release file and parse it correctly '''

    def setUp(self):
        ''' set up dummy repository and package file '''
        global drep, ddists, dcomp, darch, dmirror
        self.rep = RepositoryMirror(drep, ddists, dcomp, darch, lmirror=dmirror)
        self.dist = ddists[0]
        self.rfile = self.rep.getReleasePath(self.dist)

    #def test_ReleaseFile(self):
    #    ''' Read in Release file '''
    #    self.relfile = RelFile(self.rep, self.dist, self.rfile)

class TestPkgFile(unittest.TestCase):
    ''' Read in a Package file and parse it correctly '''

    def setUp(self):
        ''' set up dummy repository and package file '''
        global drep, ddists, dcomp, darch, dmirror
        self.rep = RepositoryMirror(drep, ddists, dcomp, darch, lmirror=dmirror)
        self.dist = ddists[0]
        self.rfile = self.rep.getReleasePath(self.dist)

if __name__ == '__main__':
    unittest.main()
