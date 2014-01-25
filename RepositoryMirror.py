#! /usr/bin/python3
'''
Updates a local mirror of a Debian Mirror.
Reads the Debian Release/Package files and computes what has changed compared to the
local mirror. Can report the changes and size of the download required for updating
and optionally update the local mirror.
'''

import urllib.request
import os
import unittest
import argparse
import sys
import tempfile
import bz2
import gzip
import shutil
import hashlib
from configparser import ConfigParser

class RepositoryMirror:
    ''' Debian Repository Mirroror - check state and optionally update 
Check a debian repository at a given URL. Repository consists of directory structure at repo:
dists directory - which contains a directory for each distribution e.g. distribution wheezy/updates would
  have a Release file at $repo/dists/wheezy/updates/Release describing the components of that distribution.

This might list a Package file contrib/binary-all/Packages.bz2 which would be at
    $repo/dists/wheezy/updates/contrib/binary-all/Packages.bz2

Release.gz - Release file defining all the distributions in this Release
    Consists of some header lines defining Suite, Validity Date, architecture list, component list followed by
    lists of package files in the format:
<checksum> <size> <PackageFile> 
...

Packages.gz - List of Debian package entries - seperated by blank lines. Each entry contains:
Package-name, Description, Architecture, Filename, Size amongst others.

   frozensets of Package filenames calculated between original Release and new Release:
 rm_pkgs = removed from version of Release file
 com_pkgs = common between Release file
 new_pkgs = new in new Release file.

Dictionaries:
    relfiles - RelFile => Release File info
    pkgfiles - PkgFile => Package file info
    debfiles - DebFile => Debian Package info
    '''
    def __init__(self, repo=None, dists=None, comps=None, archs=None, lmirror=None):
        ''' Mirror subset of a debian repository - configurable subset of distributions/components/architectures
    repo - base URL of repository
    dists - distributions 
    comps - components 
    archs - architectures 
    lmirror - local directory to mirror 
        '''

        self.repo = repo = repo if repo else RepositoryMirror.repository
        self.dists = dists if dists else RepositoryMirror.distributions
        self.comps = comps if comps else RepositoryMirror.components
        self.archs = archs if archs else RepositoryMirror.architectures
        if lmirror:
            self.lmirror = lmirror
        else:
            self.lmirror = os.path.basename(self.repo)
        self.updated = False
        self.changed_dists = []

        self.relfiles = {}
        self.pkgfiles = {}
        self.debfiles = {}

    cfgFile="RM.cfg"
    repository = 'http://web/security.debian.org'
    distributions = 'wheezy/updates squeeze/updates jessie/updates'
    components = 'main contrib non-free'
    architectures = 'amd64 all'
    tdir = 'tmp' # temporary directory prefix

    def dump_info(self):
        '''Print details of the configuration'''
        print("Configuration file: ", self.cfgFile)
        print("Repository: ", self.repository)
        print("distributions: ", self.distributions)
        print("components: ", self.components)
        print("architectures: ", self.architectures)

    def config(cf=cfgFile):
        ''' Set up configuration - optionally read from RM.cfg'''
        if not os.access(RepositoryMirror.cfgFile, os.R_OK):
            return

        cfg = ConfigParser()
        cfg.read(RepositoryMirror.cfgFile)
        setup = cfg['setup']
        RepositoryMirror.repository = setup.get('repository', RepositoryMirror.repository)
        RepositoryMirror.distributions = setup.get('distributions', RepositoryMirror.distributions).split()
        RepositoryMirror.components = setup.get('components', RepositoryMirror.components).split()
        RepositoryMirror.architectures = setup.get('architectures', RepositoryMirror.architectures).split()
        RepositoryMirror.tdir = setup.get('tdir', RepositoryMirror.tdir)

    def getPackagePath(self, dist=distributions[0], comp=components[0],
            arch=architectures[0]):
        ''' Return a Package path for the given distribution/component/architecture'''

        #print("getPackagePath(%s, %s, %s, %s, %s, %s)" % (self.lmirror, 'dists', dist, comp, 'binary-'
        #    + arch,  'Packages.bz2'))
        p = os.path.join(self.lmirror, 'dists', dist, comp, 'binary-' + arch,  'Packages.bz2')
        return p

    def getReleasePath(self, dist=distributions[0]):
        ''' Return a Release file path for the given distribution'''

        p = os.path.join(self.lmirror, 'dists', dist, 'Release')
        return p

    def getDebPath(self, filename):
        ''' Return a Debian package file path for the given filename'''

        p = os.path.join(self.lmirror, filename)
        return p

    def getPackageURL(self, dist=distributions[0], comp=components[0],
            arch=architectures[0]):
        ''' Return a Package file URL for the given distribution/component/architecture'''

        url = self.repo + '/dists/' + dist + '/' + comp + '/binary-' + arch + '/Packages.bz2'
        return url

    def getReleaseURL(self, dist=distributions[0]):
        ''' Return a Release file URL for the given distribution'''

        url = self.repo + '/dists/' + dist + '/Release'
        return url

    def getDebURL(self, filename):
        ''' Return a Debian Package URL for the Filename'''

        url = self.repo + '/' + filename
        return url

    def checkPackage(self, rel, pname):
        '''
        Check the local mirror of Package pname and it's debian packages
        '''
        global args

        pkg = rel.pkgs[pname]
        #print('checkPackage(rel=%s comp=%s arch=%s size=%s, md5sum=%s)'
        #        % (rel.name, pkg.comp, pkg.arch, pkg.size, pkg.md5sum))
        path = self.getPackagePath(rel.name, pkg.comp, pkg.arch)
        url = self.getPackageURL(rel.name, pkg.comp, pkg.arch)
        pkg.cfile = cfile = CacheFile(url, ofile=path)
        if not cfile.check(size=pkg.size, md5sum=pkg.md5sum):
            if args.verbose:
                print("checkPackage(path=%s url=%s) - missing" % (path, url))
            cfile.fetch()
            pfile = cfile.tfile
            pkg.modified = True
        else:
            if args.verbose:
                print("checkPackage(path=%s url=%s) - ok" % (path, url))
            pfile = cfile.ofile
            pkg.modified = False

        if args.verbose:
            print("checkPackage() - processing %s" % pfile)
        pkg.rdPkgFile(pfile)
        return pkg

    def skeletonCheck(self, create=False):
        '''Checks the mirror skeleton directores are present and possibly create them
        If not present and create=True it will attempt to create the directories
        It returns false if not present and create=False. If create=True it attempts to create them
        returns True if it succeeds. Directories expected/checked for are: 
            repro
            repro/dists/<dist>/ - for each <dist> defined.

            Creates tempdir - used for temporary/cache files
            Sets CacheFile.tdir - used as prefix for all CacheFile creations 
        '''
        global args
        v, n, nn = args.verbose, args.dry_run, args.very_dry_run
        if nn: n = True

        # Check for missing skeleton directories
        if create == False:
            if not os.path.isdir(self.lmirror):
                print("No local mirror %s - try -create option?" % self.lmirror)
                return False

            for d in self.dists:
                dpath = os.path.join(self.lmirror, 'dists', d)
                if os.path.isdir(dpath) == False:
                    if args.verbose:
                        print(("Missing mirror release directory: %s\n" +
                            " - use -create to force it's creation") % dpath)
                    return False
        else:
            for d in self.dists:
                reldir = os.path.join(self.lmirror, 'dists', d)
                if os.path.isdir(reldir) == False:
                    print("%s missing - creating" % reldir)
                    try:
                        if n:
                            print("mkdirs %s" % reldir)
                        else:
                            os.makedirs(reldir)
                    except OSError:
                        print("Failed - unable to create directory %s!" % reldir)
                        return False

        try:
            tdir = os.path.join(self.lmirror, RepositoryMirror.tdir + 'XXXX')
            if nn:
                print("mkdirs %s" % tdir)
                self.tdir = tdir
            else:
                self.tempDir = tempfile.TemporaryDirectory(
                            prefix=RepositoryMirror.tdir,
                            dir=self.lmirror)
                self.tdir = self.tempDir.name
        except OSError:
            print("Failed to create temporary directory %s" % tdir)
            return False

        if v: print("Created Temporary Directory %s" % self.tdir)
        CacheFile.tdir = self.tdir

        return True

    def update(self):
        '''
Update Mirror's status by reading repository's state
Loops through the distributions specified and computes change_dists list
of distribution and releaseCacheFile lists.
        '''
        global args
        cnt = 0 # no. of changed files
        missing = 0 # missing bytes of files

        for d in self.dists:
            if args.verbose:
                print('Checking Release %s' % d)
            r = self.checkRelease(d)
            if args.verbose:
                print('%s - Release file %schanged' % (d, "" if r else "un"))
            if r != None:
                self.changed_dists.append([d, r])
                self.updated = True

        for r in self.relfiles.values():
            for p in r.pkgs:
                pkg = self.checkPackage(r, p)
                if pkg.modified:
                    self.updated = True
                    pkg.cfile.update()
                    cnt += 1
                if pkg.total_missing > 0:
                    self.updated = True
                    missing += pkg.total_missing

        if args.verbose:
            print('%d changed package files - %d missing for downloading' % (cnt, missing))
        return self.updated

    def checkRelease(self, dist):
        ''' Read given Release file and return Release object if has changed

Argument: dist - name of distribution e.g. wheezy/updates
Returns:
    None - Release file hasn't changed from the Mirror Version
    rfile = CacheFile object of the updated Release file
        '''

        global args

        if args.verbose:
            print("Checking Release %s ..." % dist)

        rURL = self.getReleaseURL(dist=dist)
        rfile = CacheFile(rURL, self.getReleasePath(dist=dist))
        if not rfile.fetch():
            self.cleanUp(1, "Unable to fetch %s - aborting..." % rURL)
        if rfile.match():
            oRelFile = RelFile(self, dist, rfile.ofile)
            self.relfiles[dist] = oRelFile
            oldPkgs = frozenset(oRelFile.pkgs)
            self.com_pkgs = oldPkgs
            self.new_pkgs = self.rm_pkgs = frozenset([])
            if args.verbose:
                print("No Changes in %s - total %d files" % (dist, len(self.com_pkgs)))
                for p in self.com_pkgs:
                    print("%s" % p)
                print()
            return None

        if args.verbose:
            print("%s has changed" % dist)
        oRelFile = RelFile(self, dist, rfile.ofile)
        nRelFile = RelFile(self, dist, rfile.tfile)
        self.relfiles[dist] = nRelFile
        newPkgs = frozenset(nRelFile.pkgs)
        oldPkgs = frozenset(oRelFile.pkgs)
        self.new_pkgs = newPkgs - oldPkgs
        if len(self.new_pkgs) > 0 and args.verbose:
            print("%d new packages:" % len(self.new_pkgs))
        self.rm_pkgs = oldPkgs - newPkgs
        if len(self.rm_pkgs) > 0 and args.verbose:
            print("%d packages removed:" % len(self.rm_pkgs))
        self.com_pkgs = newPkgs & oldPkgs
        if args.verbose:
            print("%d common packages:" % len(self.com_pkgs))
        i = 0
        for p in newPkgs:
            print("%d: %s" % (i, p))
            i += 1
        return rfile

    def cleanUp(self, ret=0, msg=None):
        '''Remove all temporary files/directories'''

        if msg:
            print(msg)
        self.tempDir.cleanup()
        sys.exit(ret)


class RelFile():
    ''' List of Package files in Release 
Holds summary of a Release file including:
   name - Release name
   info - dict of parameters from head of release file
   pkgs - dict of PkgFile index by pkgfile names matching RepositoryMirror's parameters
    '''

    def __init__(self, rep, name, rfile):
        ''' Reads in a Release from given path name
        rep - Repository Mirror
        name - Release Name
        rfile - full path to Release file
        '''

        self.repMirror = rep
        self.name = name
        self.info = {}
        self.pkgs = {}
        self.changed = False

        if not os.access(rfile, os.R_OK):
            return
        fp = open(rfile, 'rt')
        for l in fp:
            l = l.lstrip().rstrip()
            w = l.split()
            #print('%s - w=%s' % (repr(l), repr(w)))
            if w[0] in { 'MD5Sum:', 'SHA1:', 'SHA256:' }:
                break
            if w[0][-1] == ':':
                self.info[w[0][0:-1]] = ' '.join(w[1:])
                continue
            print("RelFile: %s Ignoring strange word %s" % (rfile, w[0]))

        for l in fp:
            l = l.lstrip().rstrip()
            w = l.split()
            if w[0] in { 'MD5Sum:', 'SHA1:', 'SHA256:' }:
                break
            if len(w) > 2:
                f = w[2]
                (comp, arch, ctype) = parsePfile(f)
                if ctype == 'bzip' and comp in RepositoryMirror.components \
                    and arch in RepositoryMirror.architectures :
                    self.pkgs[f] = PkgFile(rep, f, md5sum=w[0], size=w[1])
                continue
            print("RelFile '%s' %d unknown package line: %s" % (rfile, len(w), l))
        fp.close()

class PkgEntry():
    ''' Package file entry - usually detailing a .deb file '''
    def __init__(self, name, fname, md5sum, size):
        ''' Package file entry defining a .deb file '''
        self.name = name
        self.fname = fname
        self.md5sum = md5sum
        self.size = size

    def getPkgEntry(fp):
        '''Return a Package Entry or None from Package file fp'''
        try: 
            p = PkgEntry.rdPkgDetails(fp)
            if len(p) == 0:
                    return None

            #print("getPkgEntry() = %s" % repr(p))
            return PkgEntry(p['Package'], p['Filename'], p['MD5sum'], p['Size'])

        except OSError as e:
            print('getPkgEntry() failed: %s' % e.strerror)
            return None

    def rdPkgDetails(fp):
        '''read one Package file entry from fp into a Dict of key/values'''

        p = {}
        k, v = None, ''
        for l in fp:
            # Check for end of Package definition
            if len(l.lstrip()) == 0:
                if k:
                    p[k] = v
                return p

            if l[0] == ' ': # Continuation line
                v += l
                continue

            w = l.decode().split(':', 1)
            if k: # save any current field
                p[k] = v
            k, v = w[0], w[1].strip()

        return p

class PkgFile():
    ''' Dictionary of Package File information including md5sum, file name, architecture
       pkgs[deb package name] = PkgEntry
       pkgfiles[deb package file name ] = PkgEntry
       total_missing = size in bytes of all missing / out of date packages
    '''
    def __init__(self, rep, name, md5sum=0, size=0):
        ''' Create Package File info '''
        self.repMirror = rep
        self.name = name
        if name.endswith('.bz2'):
            ctype = 'bz2'
        elif rfile.endswith('.gz'):
            ctype = gzip
        else:
            ctype = 'plain'
        self.ctype = ctype
        self.md5sum = md5sum
        self.size = size
        p = parsePfile(name)
        self.comp, self.arch = p[0], p[1]

    def rdPkgFile(self, rfile):
        ''' Read in from a Package file, update state of .deb files
        '''

        self.total_missing = 0
        if self.ctype.endswith('bz2'):
            fp = bz2.BZ2File(rfile, 'r')
        elif self.ctype.endswith('gzip'):
            fp = gzip.open(rfile, 'r')
        else:
            fp = open(rfile, 'rt')

        # read in Package entry seperated by blank lines
        self.pkgs = {}
        self.pkgfiles = {}
        while True:
            p = PkgEntry.getPkgEntry(fp)
            if p == None:
                break;
            fn = p.fname
            f = self.repMirror.getDebPath(fn)
            u = self.repMirror.getDebURL(fn)
            s = p.size
            cfile = CacheFile(u, ofile=f)
            if not cfile.check(size=s, md5sum=p.md5sum):
                p.missing = True
                p.cfile = cfile
                self.total_missing += int(s)
            else:
                p.missing = False
            self.pkgs[p.name] = p
            self.pkgfiles[p.fname] = p

        fp.close()
        if self.total_missing > 0:
            if  self.total_missing < 1024*1024:
                print("Package %s download size=%d" % (self.name, self.total_missing))
            if  self.total_missing < 1024*1024*1024:
                print("Package %s download size=%dMb " % (self.name, self.total_missing/(1024*1024)))
            else:
                print("Package %s download size=%dGb " % (self.name, self.total_missing/(1024*1024*1024)))

class CacheFile:
    ''' Cache a file locally from a URL allowing comparisons and updates of the local version '''

    tdir = 'tmp'
    tfile = 'tmp.txt'
    ofile = 'orig.txt'
    BUFSIZE = 4024

    def __init__(self, url, ofile=None, tfile=None):
        ''' URL and local original file of object to cache

            url : URL of object we cache locally
            ofile : original (local) version of file
            tfile : temporary fresh copy from URL
        '''
        self.url = url
        if ofile:
            self.ofile = ofile
        else:
            self.ofile = os.path.join(CacheFile.tdir, CacheFile.ofile)
        self.tfile = tfile

    def fetch(self, tfile=None):
        ''' fetch a fresh copy of the file into tfile '''

        global args

        try:
            if tfile:
                self.tfile = tfile
                of = open(tfile, 'wb')
            elif self.tfile:
                tfile = self.tfile
                of = open(tfile, 'wb')
            else:
                of = tempfile.NamedTemporaryFile(dir=CacheFile.tdir,
                    prefix=os.path.basename(self.ofile) + '_',
                    delete=False)
                self.tfile = of.name

            if args.verbose:
                print("Fetching %s -> %s" % (self.url, self.tfile))

            uf = urllib.request.urlopen(self.url)

            while True:
                b = uf.read(CacheFile.BUFSIZE)
                if not b: break
                of.write(b)

            uf.close()
            of.close()
            return True

        except OSError:
            return False

    def check(self, size=None, md5sum=None):
        '''
        Return True if the cached file is present and matches given size and md5sum if not None
        '''
        global args
        try:
            if not os.access(self.ofile, os.R_OK):
                if args.verbose:
                    print('Missing file - %s' % self.ofile)
                return False
            if size != None and int(size) != os.path.getsize(self.ofile):
                #print("check(size=%d) != %d - %s" % (int(size), os.path.getsize(self.ofile), self.ofile))
                return False

            if md5sum == None: return True

            m = hashlib.md5()
            with open(self.ofile, 'rb') as of:
                while True:
                    bof = of.read(CacheFile.BUFSIZE)
                    if len(bof) == 0:
                        break
                    m.update(bof)
                if md5sum != m.hexdigest():
                    print("check(md5sum=%s) != %s - %s" % (md5sum, m.hexdigest(), self.ofile))
                    return False
                return True

        except OSError:
            return False

    def match(self, ofile=None, tfile=None):
        '''Return True if the cached file matches the original file
        Assumes tfile has been fetched.
        ofile - if set uses this file to compare against cached file'''
        if ofile == None: ofile = self.ofile
        if tfile == None: tfile = self.tfile
        try:
            if os.path.getsize(self.tfile) != os.path.getsize(ofile):
                return False

            with open(tfile, 'rb') as tf, open(ofile, 'rb') as of:
                btf = tf.read(CacheFile.BUFSIZE)
                bof = of.read(CacheFile.BUFSIZE)
                while True:
                    if bof == btf and len(bof) > 0:
                        btf = tf.read(CacheFile.BUFSIZE)
                        bof = of.read(CacheFile.BUFSIZE)
                        continue
                    m = min(len(bof), len(btf))
                    if m == 0: return True

                    if bof[0:m] != btf[0:m]:
                        return False
                    bof = bof[m:-1]
                    btf = btf[m:-1]
                    if len(btf) == 0:
                        btf = tf.read(CacheFile.BUFSIZE)
                    if len(bof) == 0:
                        bof = of.read(CacheFile.BUFSIZE)

        except OSError:
            return False

    def update(self, ofile=None, tfile=None):
        '''Replace the original file with the cached file tfile
        ofile = over write this file instead of currently set original file
        tfile = use this for the new file to replace the original file with
        '''

        global args
        if ofile == None:
            ofile = self.ofile
        if tfile == None:
            tfile = self.tfile
        try:
            if args.verbose: print('rename %s => %s' % (tfile, ofile))
            if args.dry_run:
                print('mv %s %s' % (tfile, ofile))
            else:
                os.rename(tfile, ofile)
            return True

        except OSError as e:
            dname = os.path.dirname(ofile)
            if os.path.isdir(dname) == False:
                print("%s missing - creating" % dname)
                try:
                    if args.dry_run:
                        print("mkdirs %s" % dname)
                    else:
                        os.makedirs(dname)
                        os.rename(tfile, ofile)
                        if os.access(ofile, os.R_OK):
                            print("Created %s" % ofile)
                            return True
                except OSError:
                    print("Failed - unable to create directory %s!" % dname)
                    return False

            print('mv %s %s failed: %s' % (tfile, ofile, e.strerror))
            return False

def parsePfile(s):
    ''' Parse package line from Release file into tuple (component, arch, ctype)'''
    l = s.split('/')
    if l[1].startswith('binary-'):
        arch = l[1][len('binary-'):]
    elif l[1] == 'source':
        arch = l[1]
    else: arch = 'other'

    e = l[-1]
    if e == 'Packages':
        ctype = 'plain'
    elif e.endswith('Packages.gz'):
        ctype = 'gzip'
    elif e.endswith('Packages.bz2'):
        ctype = 'bzip'
    else: ctype = 'unknown'

    return (l[0], arch, ctype)

class TestRepositoryMirror(unittest.TestCase):
    v = False

    def setUp(self):
        global args
        if args.verbose: TestRepositoryMirror.v = True
        else: TestRepositoryMirror.v = False

        self.repMirror = RepositoryMirror()
        self.pURL = self.repMirror.getPackageURL()
        self.rURL = self.repMirror.getReleaseURL()
        os.makedirs(RepositoryMirror.tdir)
        self.cf = CacheFile(self.pURL)

    def tearDown(self):
        shutil.rmtree(RepositoryMirror.tdir)

    def test_RepositoryMirror(self):
        if TestRepositoryMirror.v: print("RepositoryMirror Tests")
        if TestRepositoryMirror.v: print("getPackageURL() = " + self.pURL)
        if TestRepositoryMirror.v:("getReleaseURL() = " + self.rURL)
        self.assertTrue(self.repMirror.skeletonCheck(create=True))

    def test_CacheFile(self):
        if TestRepositoryMirror.v:("CacheFile Tests")

        if self.cf:
            self.assertTrue(self.cf)
            if TestRepositoryMirror.v: print("Created CacheFile(cf)")

        tfile = '/tmp/release.txt_new'
        # Remove any existing original
        try:
            os.unlink(tfile)
        except OSError:
            pass # ignore if file is missing

        if self.cf.fetch(tfile):
            self.assertTrue(True)
            if TestRepositoryMirror.v: print("CacheFile - test fetch file to " + tfile)
        else:
            self.assertTrue(False)

        ofile = '/tmp/release.txt'
        # Remove any existing original
        try :
            os.unlink(ofile)
        except OSError:
            pass
        # Test match will fail with no original
        if self.cf.match(ofile):
            if TestRepositoryMirror.v: print("Failure: Testing Match against missing file succeeded!- should have failed!")
            self.assertTrue(False)
        else:
            self.assertTrue(True)
            if TestRepositoryMirror.v: print("Passed: Match against missing file - failed!")

        # Test update will work create original when it doesn't exist
        if self.cf.update(ofile):
            self.assertTrue(True)
            if TestRepositoryMirror.v: print("Passed: Update of missing file worked")
        else:
            self.assertTrue(False)


        # Test re-fetch will now match
        if self.cf.fetch(tfile):
            if TestRepositoryMirror.v: print("Passed: Re-fetching original file worked")
            self.assertTrue(True)
        else:
            self.assertTrue(False)

        if self.cf.match(ofile):
            if TestRepositoryMirror.v: print("Passed: Matching original file with newly updated works!")
            self.assertTrue(True)
        else:
            if TestRepositoryMirror.v: print("Failed: Matching original file with newly updated failed!")
            self.assertTrue(False)

    def test_RelFile(self):
        if TestRepositoryMirror.v: print("RelFile Tests")
        r = 'Release'
        self.assertTrue(os.access(r, os.R_OK))
        rf = RelFile(self, r)
        if TestRepositoryMirror.v:
            print("RelFile Tests")
            for k in rf.info.keys():
                print('%s - %s' % (k, rf.info[k]))

        print("Reading Release file %s : %d Package files" % (r, len(rf.pkgs)))

    def test_PkgFile(self):
        if TestRepositoryMirror.v: print("Package File Tests")
        r = 'Packages.gz'
        self.assertTrue(os.access(r, os.R_OK))
        pf = PkgFile(r)
        pf.rdPkgFile(r)

        print("Reading Package file %s - %d Package definitions" % (r, len(pf.pkgs)))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Mirror A Debian Repository')

    parser.add_argument('-c', dest='cfgFile', default='RM.cfg',
        help='configuration file that defines repository to mirror')
    parser.add_argument('-info', dest='info', action='store_true',
        help='Print details of the Repository and exit')
    parser.add_argument('-n', dest='dry_run', action='store_true',
        help='Do not execute commands - print them. But creates temporary files')
    parser.add_argument('-N', dest='very_dry_run', action='store_true',
        help='Do not even create temporary files')
    parser.add_argument('-v', dest='verbose', action='store_true',
        help='verbose mode')
    parser.add_argument('-run_tests', dest='run_tests', action='store_true',
        help='Run unit tests')
    parser.add_argument('-create', dest='create', action='store_true',
        help='Create Repository if missing')
    parser.add_argument('-fetch', dest='fetch', action='store_true',
        help='fetch missing packages')

    args = parser.parse_args()

    if args.run_tests:
        verbose = 2 if args.verbose else 1
        suite = unittest.TestLoader().loadTestsFromTestCase(TestRepositoryMirror)
        unittest.TextTestRunner(verbosity=verbose).run(suite)
        sys.exit(0)

    RepositoryMirror.cfgFile = args.cfgFile
    RepositoryMirror.config()
    repM = RepositoryMirror()

    if args.info:
        repM.dump_info()
        sys.exit(0)

    nfails = 0
    if repM.skeletonCheck(args.create) != True:
        print("Unable to set up repository mirror for %s at %s"
            % (repM.repository, repM.lmirror))
        sys.exit(1)
    if repM.update() == False:
        print("%s: Repository Mirror at %s is up to date"
            % (repM.repository, repM.lmirror))
        sys.exit(0)

    print("%s: %d release%s changed:" %
        (repM.repository, len(repM.changed_dists), ("" if len(repM.changed_dists) == 1 else "s")))
    for r in repM.changed_dists:
        print('   ' + r[0] + ': ', end='')
        if r[1].update():
            print('updated ok')
        else:
            print('update failed!')
            nfails += 1

    if args.fetch:
        for r in repM.relfiles.values():
            for p in r.pkgs.values():
                for d in p.pkgs.values():
                    if d.missing:
                        print("Fetching %s - size %s" % (d.name, d.size))
                        d.cfile.fetch()
                        d.cfile.update()

    sys.exit(nfails)
