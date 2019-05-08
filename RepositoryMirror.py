#! /usr/bin/python3
'''
Updates a local mirror of a Debian Mirror.
Reads the Debian Release/Package files and computes what has changed compared to
the local mirror. Can report the changes and size of the download required for
updating and optionally update the local mirror.
'''

import urllib.request
import os
import shutil
import unittest
import argparse
import sys
import tempfile
import bz2
import gzip
import shutil
import hashlib
import stat
#import time
from configparser import ConfigParser
# Handle python version dependancies...
from sys import version

verbose = False
extra_verbose = False
dry_run = False
very_dry_run = False
check_md5sum = True

os.umask(0o22)


version = version.split()[0]

if version >= '3.3':
    from time import perf_counter as gettime
else:
    from time import time as gettime


def checkFile(file, size=None, md5sum=None):
    '''
    Return True if the file is present and matches given size and/or md5sum
    If None is given that field is NOT checked
    '''
    try:
        if not os.access(file, os.R_OK):
            if verbose:
                print('Missing file - %s' % file)
            return False
        if size != None and int(size) != os.path.getsize(file):
            return False

        if md5sum == None: return True

        m = hashlib.md5()
        with open(file, 'rb') as of:
            while True:
                bof = of.read(CacheFile.BUFSIZE)
                if len(bof) == 0:
                    break
                m.update(bof)
            if md5sum != m.hexdigest():
                print("checkFile(md5sum=%s) != %s - %s" % (md5sum, m.hexdigest(), file))
                return False
            return True

    except OSError:
        return False

class RepositoryMirror:
    ''' Debian Repository Mirroror - check state and optionally update
Check a debian repository at a given URL. Repository consists of directory structure at repo:
dists directory - which contains a directory for each distribution e.g. distribution wheezy/updates would
  have a Release file at $repo/dists/wheezy/updates/InRelease describing the components of that distribution
  wrapped with a Hash and Signature There is a plain Release file with a detacted signature in Release.gpg.

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
        self.lmirror = lmirror if lmirror else RepositoryMirror.lmirror
        self.debList = {} # package file -> list of deb entries
        if RepositoryMirror.pkgLists:
            self.parsePkgLists(RepositoryMirror.pkgLists)
        else:
            self.pkgLists = None
        self.updated = False
        self.changed_dists = []

        self.relfiles = {}
        self.pkgfiles = {}
        self.debfiles = {}
        self.cnt = 0

    cfgFile="RM.cfg"
    repository = 'http://web/security.debian.org'
    distributions = 'wheezy/updates squeeze/updates jessie/updates'.split()
    components = 'main contrib non-free'.split()
    architectures = 'amd64 all'.split()
    tdir = 'tmp' # temporary directory prefix
    lmirror = os.path.basename(repository)
    pkgLists = None # By default will mirror *all* deb packages

    def dump_info(self):
        '''Print details of the configuration'''
        print(self)
        self.skeletonCheck(False)

    def config(cf=cfgFile):
        ''' Set up configuration - optionally read from RM.cfg'''
        if not os.access(RepositoryMirror.cfgFile, os.R_OK):
            return

        cfg = ConfigParser()
        cfg.read(RepositoryMirror.cfgFile)
        setup = cfg['setup']
        RepositoryMirror.repository = setup.get('repository', RepositoryMirror.repository)
        d = setup.get('distributions', None)
        if d:
            RepositoryMirror.distributions = d.split()
        d = setup.get('components', None)
        if d:
            RepositoryMirror.components = d.split()
        d = setup.get('architectures', None)
        if d:
            RepositoryMirror.architectures = d.split()
        RepositoryMirror.tdir = setup.get('tdir', RepositoryMirror.tdir)
        RepositoryMirror.lmirror = setup.get('lmirror', RepositoryMirror.lmirror)
        pL = {}
        for d in RepositoryMirror.distributions:
            print("Checking distribution '", d, " : 'packages-'" + d, "'", sep='')
            pkglist = setup.get('packages-' + d, None)
            print("pkglist for ", d, "is", pkglist)
            if pkglist:
                pL[d] = pkglist
        if len(pL) > 0:
            RepositoryMirror.pkgLists = pL

    def parsePkgLists(self, pkgLists):
        '''
    Process all Package List definitions - produces a set of packages which are to be mirrored.
    Each package list is associated with one distribution and is a dictionary of package lists
    file names. Each Package List file is the names of all the packages that should be mirrored
    of this distrubution. The following command will generate such a file called 'pkg-list'
    which will have all the packages that have been installed on the current debian box:
       awk '/^Package: / { print $2; }' /var/lib/dpkg/status > pkg-list
        '''
        global args

        self.pkgLists = pkgLists
        for k in pkgLists:
            pf = pkgLists[k]
            if not os.access(pf, os.R_OK):
                print("Unable to read package file: ", pf)
                sys.exit(1)
            fp = open(pf, 'rt')
            pkg_names = set()
            for l in fp:
                for p in l.split():
                    pkg_names.add(p)
            fp.close()
            if args.verbose:
                print("Read %d names from %s package list %s" %
                    (len(pkg_names), k, pf))
            self.debList[k] = pkg_names


    def getPackagePath(self, dist, pkg):
        ''' Return a Package path for the given distribution/component/architecture'''

        #print("getPackagePath(%s, %s, %s, %s, %s, %s)" % (self.lmirror, 'dists', dist, comp, 'binary-'
        #    + arch,  'Packages.bz2'))
        #p = os.path.join(self.lmirror, 'dists', dist, comp, 'binary-' + arch,  'Packages.bz2')
        p = os.path.join(self.lmirror, 'dists', dist, pkg.name)
        return p

    def getReleasePath(self, dist=distributions[0], file_name='Release'):
        ''' Return a Release file path for the given distribution'''

        p = os.path.join(self.lmirror, 'dists', dist, file_name)
        return p

    def getReleaseURL(self, dist=distributions[0], file_name='Release'):
        ''' Return a Release file URL for the given distribution'''

        url = self.repo + '/dists/' + dist + '/' + file_name
        return url

    def mkCacheFile(self, dist, fname):
        ''' Return a Cache file for a given distribution file '''

        rURL = self.getReleaseURL(dist, fname)
        cfile = CacheFile(rURL, self.getReleasePath(dist, fname))
        return cfile

    def getDebPath(self, filename):
        ''' Return a Debian package file path for the given filename'''

        p = os.path.join(self.lmirror, filename)
        return p

    def getPackageURL(self, dist, pkg):
        ''' Return a Package file URL for the given distribution/component/architecture'''

        #url = self.repo + '/dists/' + dist + '/' + comp + '/binary-' + arch + '/Packages.bz2'
        url = self.repo + '/dists/' + dist + '/' + pkg.name
        return url

    def getDebURL(self, filename):
        ''' Return a Debian Package URL for the Filename'''

        url = self.repo + '/' + filename
        return url

    def checkRelEntryFile(self, rel, pname, update=True):
        '''
        Check the Release Entry file pname on the local mirror
        '''
        pkg = rel.otherFiles[pname]
        if verbose:
            print('checkRelEntryFile(rel=%s comp=%s arch=%s size=%s, md5sum=%s)'
                % (rel.name, pkg.comp, pkg.arch, pkg.size, pkg.md5sum))
        path = self.getPackagePath(rel.name, pkg)
        url = self.getPackageURL(rel.name, pkg)
        pkg.cfile = cfile = CacheFile(url, ofile=path)
        if check_md5sum:
            md5sum = pkg.md5sum
        else:
            md5sum = None
        if not cfile.check(size=pkg.size, md5sum=md5sum):
            if update:
                try:
                    cfile.fetch()
                    pfile = cfile.tfile
                    pkg.modified = True
                    pkg.missing = False
                except:
                    pkg.missing = True
            else:
                pkg.missing = True
        else:
            if verbose:
                print("checkRelEntryFile(path=%s url=%s) - ok" % (path, url))
            pfile = cfile.ofile
            pkg.modified = False
            pkg.missing = False

        if pkg.missing:
            print(' Warning: %s - Release Entry file %s missing' % (rel.name, pname))
            if verbose:
                print("Release entry file (path=%s url=%s) - missing" % (path, url))
        return pkg

    def checkPackage(self, rel, pname, update=True):
        '''
        Check the Package file pname on the local mirror and it's debian packages
        '''

        pkg = rel.pkgFiles[pname]
        if verbose:
            print('checkPackage(rel=%s comp=%s arch=%s size=%s, md5sum=%s)'
                % (rel.name, pkg.comp, pkg.arch, pkg.size, pkg.md5sum))
        path = self.getPackagePath(rel.name, pkg)
        url = self.getPackageURL(rel.name, pkg)
        pkg.cfile = cfile = CacheFile(url, ofile=path)
        if check_md5sum:
            md5sum = pkg.md5sum
        else:
            md5sum = None
        if not cfile.check(size=pkg.size, md5sum=md5sum):
            if update:
                try:
                    cfile.fetch()
                    pfile = cfile.tfile
                    pkg.modified = True
                    if checkFile(pfile, size=pkg.size, md5sum=md5sum):
                        pkg.missing = False
                        cfile.update()
                        pfile = cfile.ofile
                    else:
                        print("Updated Package file %s doesn't match" % pkg.name)
                        pkg.missing = True
                except:
                    pkg.missing = True
            else:
                pkg.missing = True
        else:
            if verbose:
                print("checkPackage(path=%s url=%s) - ok" % (path, url))
            pfile = cfile.ofile
            pkg.modified = False
            pkg.missing = False

        if pkg.missing:
            print(' Warning: %s - package file %s missing' % (rel.name, pname))
            if verbose:
                print("package file (path=%s url=%s) - missing" % (path, url))
            return pkg
        if verbose:
            print("processing Package file %s" % pfile)
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
        v, n, nn = verbose, dry_run, very_dry_run
        if nn: n = True

        if create == False:
            if v:
                print("Check mirror's directory structure in %s" % self.lmirror)
            if not os.path.isdir(self.lmirror):
                print("No local mirror %s - try -create option?" % self.lmirror)
                return False

            for d in self.dists:
                dpath = os.path.join(self.lmirror, 'dists', d)
                if os.path.isdir(dpath) == False:
                    if verbose:
                        print(("Missing mirror release directory: %s\n" +
                            " - use -create to force it's creation") % dpath)
                    return False
        else:
            if v:
                print("Creating mirror's framework in %s" % self.lmirror)
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

    def checkState(self, update=True):
        '''
Update Mirror's State by reading repository's state
Loops through the distributions specified and computes change_dists list
of distribution and releaseCacheFile lists. If update is true will refresh
the Mirror's release details from the source repository
        '''
        global args
        cnt = 0 # no. of changed files
        missing = 0 # missing bytes of files
        self.missing = False

        if update == False:
            print('Not refreshing info from original repository')
        for d in self.dists:
            if args.verbose:
                print('Checking Release %s' % d)
            relfile = self.checkRelease(d, update)
            if not relfile.present:
                print(' Warning: %s - Release file missing' % d)
                self.missing = True;
            elif relfile.changed:
                if args.verbose:
                    print('%s - Release file changed ' % d)
                self.changed_dists.append([d, relfile.cfile])
                self.updated = True
            else:
                if args.verbose:
                    print('%s - Release file unchanged ' % d)

        for r in self.relfiles.values():
            if not r.present:
                print('Skipping Release %s as Release file %s is missing' % (r.name, r.cfile.ofile))
                continue
            if args.verbose:
                print('Examining release file %s (%s)' % (r.name, r.cfile.ofile))
            for p in r.pkgFiles:
                if args.verbose:
                    print('Examining pkg file %s ' % (p))
                pkg = self.checkPackage(r, p, update)
                if pkg.missing:
                    self.updated = True
                    self.missing = True
                    cnt += 1
                    continue
                if update and pkg.modified:
                    self.updated = True
                    pkg.cfile.update()
                if pkg.total_missing > 0:
                    self.updated = True
                    missing += pkg.total_missing
                cnt += pkg.cnt
                print('Package %s - cnt %d missing %d' % (pkg.name, pkg.cnt, pkg.total_missing))
            for o in r.otherFiles:
                if args.verbose:
                    print('Examining other file %s ' % (o))
                pkg = self.checkRelEntryFile(r, o, update)
                if pkg.missing:
                    self.updated = True
                    self.missing = True
                    cnt += 1
                    continue
                if update and pkg.modified:
                    self.updated = True
                    pkg.cfile.update()
                    print('Updating File %s' % (pkg.name ))
                #if pkg.total_missing > 0:
                #    self.updated = True
                #    missing += pkg.total_missing
                #cnt += pkg.cnt
                #print('Other File %s - needs updating' % (pkg.name ))
            if args.verbose:
                print('Release %s - total %d' % (r.name, len(r.pkgFiles)))
            r.cnt = cnt
            self.cnt += cnt
            cnt = 0

        if args.verbose:
            print('%d changed files - %d bytes missing for downloading' % (self.cnt, missing))
        return self.updated

    def checkRelease(self, dist, update):
        ''' Read given Release file and return Release object
Argument: dist - name of distribution e.g. wheezy/updates
          update - if true, fetch latest release file from original repository
Returns:
    Release file

    Checks for Release.gpg - detached signature - if present uses that and sets flag has_sig
    if not present uses InRelease file, if not present fails
        '''

        global args

        if args.verbose:
            print("Looking for Release file for %s ..." % dist)

        sig_cfile = self.mkCacheFile(dist, "Release.gpg")
        has_sig = False # => signature file not present
        # Set has_sig = True if we find a signature file
        if update:
            if sig_cfile.fetch():
                has_sig = True
        else:
            if os.access(sig_cfile.ofile, os.R_OK):
                has_sig = True

        if has_sig:
            rel_name = "Release"
            inrel_cfile = self.mkCacheFile(dist, "InRelease")
            if update:
                if args.verbose:
                    print(" Fetching InRelease file - %s -> %s..." %
                        (inrel_cfile.url, inrel_cfile.ofile))
                if inrel_cfile.fetch():
                    inrel_cfile.update()
        else:
            rel_name = "InRelease"
        cfile = self.mkCacheFile(dist, rel_name)
        #rURL = self.getReleaseURL(dist, rel_name)
        #cfile = CacheFile(rURL, self.getReleasePath(dist, rel_name))
        #cRelFile = None
        if has_sig:
            if args.verbose:
                print(" Found detached signature using - %s ..." % rel_name)
        else:
            if args.verbose:
                print(" No detached signature using - %s ..." % rel_name)
            sig_cfile = None
        #print("has_sig:", has_sig, " rel_name=", rel_name, " update=", update)
        cRelFile = self.checkReleaseFile(dist, cfile, update, sig_cfile)
        if cRelFile == None:
            cRelFile = RelFile(self, dist, cfile.ofile, sig_cfile)
        self.relfiles[dist] = cRelFile
        cRelFile.cfile = cfile
        return cRelFile



    def checkReleaseFile(self, dist, cfile, update, sig_cfile):
        ''' Check release file against latest version in original repository'''
        try:
            if update and not cfile.fetch():
                print("Unable to fetch Release " + dist + " definition file at " + cfile.url)
                return None
            if update and sig_cfile and not sig_cfile.fetch():
                print("Unable to fetch Release Signature file at " + cfile.url)
                return None
        except:
            self.cleanUp(1, "Unable to fetch %s - aborting..." % rURL)
            return None

        if not update or cfile.match():
            oRelFile = RelFile(self, dist, cfile.ofile, sig_cfile)
            if update and sig_cfile and not sig_cfile.match():
                if args.verbose:
                    print("%s updating missing signature file" % dist)
                    sig_cfile.update()
            oldPkgs = frozenset(oRelFile.pkgFiles)
            self.com_pkgs = oldPkgs
            self.new_pkgs = self.rm_pkgs = frozenset([])
            if args.verbose:
                print("No Changes in %s - total %d files" % (dist, len(self.com_pkgs)))
                for p in self.com_pkgs:
                    print("%s" % p)
                print()
            return oRelFile

        if args.verbose:
            print("%s has changed" % dist)
        oRelFile = RelFile(self, dist, cfile.ofile, sig_cfile)
        nRelFile = RelFile(self, dist, cfile.tfile, sig_cfile)
        nRelFile.changed = True
        newPkgs = frozenset(nRelFile.pkgFiles)
        oldPkgs = frozenset(oRelFile.pkgFiles)
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
        return nRelFile

    def cleanUp(self, ret=0, msg=None):
        '''Remove all temporary files/directories'''

        if msg:
            print(msg)
        try:
            self.tempDir.cleanup()
        except:
            print("Nothing to remove")
        sys.exit(ret)

    def __repr__(self):
        return "RepositoryMirror(repo='{}', dists={}, comps={}, archs={}, lmirror='{}')".format(
            self.repo, self.dists, self.comps, self.archs, self.lmirror)
    def __str__(self):
        s = "Configuration file: " + self.cfgFile + "\n" + \
            "Repository: " + str(self.repo) + "\n" + \
            "distributions: " + str(self.dists) + "\n" + \
            "components: " + str(self.comps) + "\n" + \
            "architectures: " + str(self.archs) + "\n" + \
            "Local Mirror stored in : " + self.lmirror + "\n"
        if self.pkgLists:
            s += "Debian packages mirrored are limited by these files:\n"
            for p in self.pkgLists:
                s += format("  %s: %s (%d items)" %
                    (p, self.pkgLists[p], len(self.debList[p])))
        return s


class RelFile():
    ''' List of Package files in Release
Holds summary of a Release file including:
   name - Release name
   info - dict of parameters from head of release file
   pkgFiles - dict of PkgFile index by pkgfile names matching RepositoryMirror's parameters
    '''

    def __init__(self, rep, name, rfile, sig_cfile):
        ''' Reads in a Release from given path name
        rep - Repository Mirror
        name - Distribution/Release Name
        rfile - full path to Release file
        info - dict of Relase file fields (indexed by field)
        '''

        self.repMirror = rep
        self.rfile = rfile
        self.name = name
        self.sig = sig_cfile
        self.info = {}
        self.pkgFiles = {}
        self.otherFiles = {}
        self.changed = False
        self.present = False
        if name in rep.debList:
            self.deblist = rep.debList[name]
        else:
            self.deblist = None

        if not os.access(rfile, os.R_OK):
            self.present = False
            return

        fp = open(rfile, 'rt')
        if sig_cfile:
            l = fp.readline()
            if l.startswith('-----BEGIN PGP SIGNED MESSAGE-----'):
                l = fp.readline()
            else:
                if not sig_cfile:
                    print("Missing PGP Signed message header")
            if l.startswith('Hash:'):
                fp.readline() # skip blank line
            else:
                if verbose:
                    print("Found Signature Hash line")

        self.present = True
        for l in fp:
            if l.startswith('-----BEGIN PGP SIGNATURE-----'):
                break
            l = l.lstrip().rstrip()
            w = l.split()
            #print('%s - w=%s' % (repr(l), repr(w)))
            if len(w) <= 0: continue
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
            if len(w) > 2 and 'Packages' in w[2]:
                f = w[2]
                (comp, arch, ctype) = PkgFile.parsePfile(f)
                if ctype == 'gzip' \
                    and comp in RepositoryMirror.components \
                    and arch in RepositoryMirror.architectures :
                    self.pkgFiles[f] = PkgFile(rep, f, md5sum=w[0], size=w[1], relfile=self)
                    if verbose:
                        print("Grab package %s" % (f))
                continue
            if len(w) > 2 and 'Translation' in w[2]:
                f = w[2]
                (comp, arch, bzctype) = PkgFile.parsePfile(f)
                if comp in RepositoryMirror.components \
                    and arch == 'Translation' and f.endswith('-en.bz2') :
                    self.otherFiles[f] = PkgFile(rep, f, md5sum=w[0], size=w[1], relfile=self)
                    if verbose:
                        print("Grab Translation %s" % (f))
                continue
            if len(w) > 2 and '/dep11/' in w[2]:
                f = w[2]
                (comp, arch, bzctype) = PkgFile.parsePfile(f)
                if args.debug:
                     print("Line:%s\ndep11 - comp='%s' arch='%s' bzctype='%s' "
                                % (l, comp, arch, bzctype))
                if comp in RepositoryMirror.components \
                    and bzctype == 'gzip' \
                    and arch in RepositoryMirror.architectures  or arch == 'any':
                    self.otherFiles[f] = PkgFile(rep, f, md5sum=w[0], size=w[1], relfile=self)
                    if verbose:
                        print("Grab component %s" % (comp))
                continue
            if verbose:
                print("RelFile '%s' %d unknown package line: %s" % (rfile, len(w), l))
                if args.debug:
                     print("w[2]='%s' " % (w[2]))
        fp.close()

        fields = self.info
        self.suite = fields.get('Suite', None)
        self.codename = fields.get('Codename', None)
        self.version = fields.get('Version', None)
        self.date = fields.get('Date', None)
        self.desc = fields.get('Description', None)
        self.components = fields.get('Components', None)
        if self.components:
            self.components = self.components.split()
        self.archs = fields.get('Architectures', None)
        if self.archs:
            self.archs = self.archs.split()

        if verbose:
            print("%d packages found in RelFile %s" % (len(self.pkgFiles), rfile))

    def __repr__(self):
        return 'RelFile({!r}, {!r}, {!r}, {!r})'.format(self.repMirror, self.name, self.rfile, self.sig)

    def __str__(self):
        return 'RelFile()\n name: {!s}\n file: {!s}\n'.format(self.name, self.rfile) + \
            ' Suite: {!s}\n Codename: {!s}\n Version: {!s}\n Date: {!s}\n'.format(self.suite, self.codename, self.version, self.date) + \
            ' Components: {!r}\n Architectures: {!r}\n Description: {!s}'.format(self.components, self.archs, self.desc)

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
            l = l.decode()
            # Check for end of Package definition
            if len(l.lstrip()) == 0:
                if k:
                    p[k] = v
                return p

            if l[0] == ' ': # Continuation line
                v += l
                continue

            #w = l.decode().split(':', 1)
            w = l.split(':', 1)
            if k: # save any current field
                p[k] = v
            if len(w) >= 2:
                k, v = w[0], w[1].strip()
            else:
                print("Error rdPkgDetails - parse error line:", l, "w = ", w)
                for i in [ 1, 2, 3 ]:
                    print(fp)
                sys.exit(2)

        return p

class PkgFile():
    ''' Dictionary of Package File information including md5sum, file name, architecture
       pkgs[deb package name] = PkgEntry
       pkgfiles[deb package file name ] = PkgEntry
       total_missing = size in bytes of all missing / out of date packages
       relfile = Release we belong to
    '''
    def __init__(self, rep, name, md5sum=0, size=0, relfile=None):
        ''' Create Package File info '''
        self.repMirror = rep
        self.name = name
        self.relfile = relfile
        if name.endswith('.bz2'):
            ctype = 'bz2'
        elif name.endswith('.gz'):
            ctype = 'gzip'
        elif name.endswith('.xz'):
            ctype = 'lzma'
        else:
            ctype = 'plain'
        self.ctype = ctype
        self.md5sum = md5sum
        self.size = size
        p = PkgFile.parsePfile(name)
        self.comp, self.arch = p[0], p[1]
        self.ignored = 0

    def rdPkgFile(self, rfile):
        '''
        Read in from a Package file, update state of .deb files
          - Restricted by any pkglist associated with that release
        '''

        global args
        self.total_missing = 0
        if self.ctype.endswith('bz2'):
            fp = bz2.BZ2File(rfile, 'r')
        elif self.ctype.endswith('gzip'):
            fp = gzip.open(rfile, 'r')
        else:
            fp = open(rfile, 'rt')

        # read in Package entry seperated by blank lines
        if args.verbose:
            print("Reading %s " % (rfile))
            st_time = gettime() + 60
        self.pkgs = {}
        self.pkgfiles = {}
        self.cnt = 0
        self.total = 0
        deblist = self.relfile.deblist if self.relfile else None
        while True:
            p = PkgEntry.getPkgEntry(fp)
            if p == None:
                break;
            if args.verbose:
                if st_time < gettime():
                    st_time = gettime() + 60
                    print("Processed ", self.total, " Up to", p.name)
            self.total += 1
            if deblist and p.name not in deblist:
                self.ignored += 1
                #if self.ignored < 3:
                    #print("p is ", p.fname, p.md5sum)
                    #print("Ignoring ", p.name)
                continue
            fn = p.fname
            f = self.repMirror.getDebPath(fn)
            u = self.repMirror.getDebURL(fn)
            s = int(p.size)
            if extra_verbose:
                print("rdPkgFile() Want ", p.name, " ofile=", f)
            cfile = CacheFile(u, ofile=f)
            if args.onlypkgs:
                md5 = None
            else:
                md5 = p.md5sum
            if not cfile.check(size=s, md5sum=md5):
                p.missing = True
                p.cfile = cfile
                self.total_missing += s
                self.cnt += 1
                if args.verbose or self.cnt < 5:
                    print(' Missing %s  size %d, md5sum=%s' % (fn, s, p.md5sum))
            else:
                p.missing = False
            # May have multiple versions of the same debian package in the one release!
            self.pkgs[p.fname] = p
            self.pkgfiles[p.fname] = p

        fp.close()
        if not args.verbose and self.cnt >= 5:
            print(' .... Total %d missing debs' % self.cnt)
        if not args.verbose:
            return
        if self.total_missing > 0:
            if  self.total_missing < 1024*1024:
                sz_str = "%d" % self.total_missing
            if  self.total_missing < 1024*1024*1024:
                sz_str = "%dMb" % (self.total_missing/(1024*1024))
            else:
                sz_str = "%dGb" % (self.total_missing/(1024*1024*1024))
            print("Package %s Total %d Ignored %d Examined %d Missing %d debs %s"
                % (self.name, self.total, self.ignored, len(self.pkgs), self.cnt, sz_str))
        else:
            print("Package %s Total %d, Ignored %d Examined %d: up to date - no missing debs"
                % (self.name, self.total, self.ignored, len(self.pkgs), ))

    def parsePfile(s):
        ''' Parse package line from Release file into tuple (component, arch, ctype)'''
        l = s.split('/')
        if l[1].startswith('binary-'):
            arch = l[1][len('binary-'):]
        elif l[1] == 'source':
            arch = l[1]
        elif l[1] == 'i18n':
            arch = 'Translation'
        elif l[1] == 'dep11' and len(l) > 2:
            if l[2].startswith('Components-'):
                arch = l[2][len('Components-'):l[2].index('.')]
                c = 'Components'
            elif l[2].startswith('icons-'):
                arch = 'any'
                c = 'icons'
            else:
                arch = 'other'
            e = l[-1]
            if e.endswith('.gz'):
                ctype = 'gzip'
            elif e.endswith('.bz2'):
                ctype = 'bzip'
            elif e.endswith('.xz'):
                ctype = 'bzip'
            else:
                ctype = 'plain'
            return (c, arch, ctype)
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

            # Note: supports non-standard syntax for local
            # file "file:abc/def" means file at abd/def
            if args.dry_run:
                of.close()
                return True
            req = urllib.request.Request(self.url)
            if req.type == 'file':
                of.close()
                if args.uselinks:
                    if args.verbose:
                        print("os.link(%s, %s)" % (req.selector, self.tfile))
                    if os.access(self.tfile, os.F_OK):
                        os.unlink(self.tfile)
                    os.link(req.selector, self.tfile)
                    return True
                if args.verbose:
                    print("shutil.copy(%s, %s)" % (req.selector, self.tfile))
                # Fix Problem with tfile being readonly
                os.chmod(self.tfile, stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
                shutil.copy(req.selector, self.tfile)
                return True
            uf = urllib.request.urlopen(self.url)

            while True:
                b = uf.read(CacheFile.BUFSIZE)
                if not b: break
                of.write(b)

            uf.close()
            of.close()
            return True

        except urllib.error.HTTPError:
            print("urllib.error.HTTPError:", self.url)
            return False

        except OSError:
            print("OSError:", tfile)
            return False

    def check(self, size=None, md5sum=None):
        '''
        Return True if the cached file is present and matches given size and md5sum if not None
        '''
        return checkFile(self.ofile, size=size, md5sum=md5sum)

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
                os.chmod(ofile, stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
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
                        os.chmod(ofile, stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
                        if os.access(ofile, os.R_OK):
                            print("Created %s" % ofile)
                            return True
                except OSError:
                    print("Failed - unable to create directory %s!" % dname)
                    return False

            print('mv %s %s failed: %s' % (tfile, ofile, e.strerror))
            return False

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

        print("Reading Release file %s : %d Package files" % (r, len(rf.pkgFiles)))

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
    parser.add_argument('-d', dest='debug', action='store_true',
        help='debug mode')
    parser.add_argument('-v', dest='verbose', action='store_true',
        help='verbose mode')
    parser.add_argument('-run_tests', dest='run_tests', action='store_true',
        help='Run unit tests')
    parser.add_argument('-create', dest='create', action='store_true',
        help='Create Repository if missing')
    parser.add_argument('-fetch', dest='fetch', action='store_true',
        help='fetch missing packages')
    parser.add_argument('-uselinks', dest='uselinks', action='store_true',
        help='URLs are local files - use links to save space')
    parser.add_argument('-norefresh', dest='update', action='store_false',
        help='do not refresh status from original repository')
    parser.add_argument('-T', '--Timeout', dest='timeout', default=None,
        help='give up after this many seconds|mins|hours|days - N[smhd] ')
    parser.add_argument('-only-pkgs-md5sum', dest='onlypkgs', action='store_false',
        help='only check package file md5sums')

    args = parser.parse_args()
    verbose, dry_run, very_dry_run  = args.verbose, args.dry_run, args.very_dry_run

    if args.run_tests:
        verbose = 2 if args.verbose else 1
        suite = unittest.TestLoader().loadTestsFromTestCase(TestRepositoryMirror)
        unittest.TextTestRunner(verbosity=verbose).run(suite)
        sys.exit(0)

    if args.timeout:
        str2unit = { 's' : 1, 'm' : 60, 'h' : 3600, 'd' : 3600*24 }
        unit = args.timeout[-1:]
        if unit in str2unit:
            args.timeout = gettime() + int(args.timeout[:-1]) * str2unit[unit]
        else:
            args.timeout = gettime() + int(args.timeout) * 3600
    else:
        args.timeout = 0.

    RepositoryMirror.cfgFile = args.cfgFile
    RepositoryMirror.config()
    repM = RepositoryMirror()

    if args.info:
        repM.dump_info()
        repM.cleanUp()

    nfails = 0
    if repM.skeletonCheck(args.create) != True:
        print("Unable to set up repository mirror for %s at %s"
            % (repM.repository, repM.lmirror))
        sys.exit(1)
    if repM.checkState(args.update) == False:
        for r in repM.relfiles.values():
            if r.present:
                print("Release %s" % r)
            else:
                print('Skipping Release %s : Release file %s is missing' % (r.name, r.cfile.ofile))
        if repM.missing:
            print("%s: Repository Mirror at %s is incomplete"
                % (repM.repository, repM.lmirror))
            repM.cleanUp(1)
        else:
            print("%s: Repository Mirror at %s is up to date"
                % (repM.repository, repM.lmirror))
            repM.cleanUp(0)

    repM.cnt += len(repM.changed_dists)
    if repM.cnt > 0:
        print("%s Repository %d change%s" %
            (repM.repository, repM.cnt, ("" if repM.cnt == 1 else "s")))
    elif repM.updated:
        print("%s Repository updated" % repM.repository)
    else:
        print("%s Repository unchanged" % repM.repository)

    if args.update:
        for r in repM.changed_dists:
            if args.verbose:
                print("Updating Release %s" % r)
            else:
                print('   ' + r[0] + ': ', end='')
            if r[1].update():
                print('updated ok')
            else:
                print('update failed!')
                nfails += 1

    if args.fetch:
        if args.verbose:
            print("%d releases" % len(repM.relfiles))
            min_time = .1
            repM.report_time = 5.
        else:
            min_time = 3.0
            repM.report_time = 60.
        for r in repM.relfiles.values():
            if args.timeout and gettime() >= args.timeout:
                print("Time out expired - skipping " + str(r))
                continue;
            if args.update and r.sig:
                r.sig.update()
            print("Fetching Release %s" % r)
            if args.verbose:
                print("%d package files:" % len(r.pkgFiles))
            for p in r.pkgFiles.values():
                if args.timeout and gettime() >= args.timeout:
                    print("Time out expired skipping Package", p.name," ...")
                    break
                print("Checking package %s for missing debs" % (p.cfile.ofile))
                if p.missing:
                    print("Skip missing package %s" % (p.cfile.ofile))
                    continue
                for d in p.pkgs.values():
                    if args.timeout and gettime() >= args.timeout:
                        print("Time out expired skipping deb " + d.name + " ...")
                        break
                    p.total_fetched = 0
                    p.last_report = p.fetch_start = gettime()
                    if d.missing:
                        print("Fetching %s - size %s" % (d.name, d.size))
                        try:
                            start = gettime()
                            d.cfile.fetch()
                            d.cfile.update()
                            elapsed = gettime() - start
                            p.total_fetched += int(d.size)
                            if start - p.last_report > repM.report_time:
                                av_speed = p.total_fetched/(start - p.fetch_start)
                                print( "%s %s %s %3.1f % fetched Estimating %d seconds to complete" %
                                    (p.name, p.arch, p.comp, 100*p.total_fetched/p.total_missing, (p.total_missing - p.total_fetched)/av_speed) )
                            elif elapsed > min_time:
                                speed = (8*int(d.size)/elapsed)/1000.
                                if speed < 2000.0:
                                    print("Downloaded in %.1f seconds = %.3f kbit/s" % (elapsed, speed))
                                elif speed < 2000000.0:
                                    print("Downloaded in %.3f seconds = %.3f Mbit/s" % (elapsed, speed/1000.))
                                else:
                                    print("Downloaded in %.6f seconds = %.3f Gbit/s" % (elapsed, speed/1000000.))

                        except OSError:
                            print("Failed to fetch %s" % d.name)
                            nfails += 1

    if nfails == 0:
        repM.cleanUp(0)
    repM.cleanUp(1)
    if args.timeout and gettime() >= args.timeout:
        print("Timed out expired - incomplete download");
