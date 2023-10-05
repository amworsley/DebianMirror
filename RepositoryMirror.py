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
import subprocess
import errno
#import time
from configparser import ConfigParser
# Handle python version dependancies...
from sys import version

verbose = False
extra_verbose = False
dry_run = False
very_dry_run = False
check_hash = True
debug = 0

os.umask(0o22)

# Enable debug for detailed tracing
# Typical path from reading Release file and then the Packages files to checking
# all the mentioned .debs are present is
# RepositoryMirror.checkState()
#  - reads in the contents into r.pkgItems dict of RMItem
#  on each RMItem
#    => RelFile.checkPackageItem()
#    rdPkgFile()

version = version.split()[0]

if version >= '3.3':
    from time import perf_counter as gettime
else:
    from time import time as gettime


def checkFile(file, size=None, hash=None, type='MD5Sum'):
    '''
    Return True if the file is present and matches given size and/or md5sum
    If None is given that field is NOT checked
    '''
    try:
        global debug
        if debug > 2:
            print("checkFile(%s, size=%s, hash=%s, type=%s)" %
                (file, size, str(hash), type))
        if not os.access(file, os.R_OK):
            if verbose:
                print('Missing file - %s' % file)
            return False
        if size != None and int(size) != os.path.getsize(file):
            if verbose:
                print('file %s size=%d, expected  %d' %
                    (file, os.path.getsize(file), int(size)))
            return False

        if hash == None: return True

        if type == None or type == 'MD5Sum':
            m = hashlib.md5()
        elif type == 'SHA256':
            m = hashlib.sha256()
        else:
            print("WARNING: Ignoring unknown hash %s for file %s" %
                (type, file))
            return True
        with open(file, 'rb') as of:
            while True:
                bof = of.read(CacheFile.BUFSIZE)
                if len(bof) == 0:
                    break
                m.update(bof)
            if hash != m.hexdigest():
                if verbose:
                    print("file %s hash=%s type=%s != %s - %s"
                        % (file, hash, str(type), m.hexdigest()))
                return False
            return True

    except OSError as e:
        if verbose:
            print("file %s exception=%s" % (file, repr(e)))
        return False
    except Exception as e:
        print("Exception %s " % repr(e))
        import traceback, sys
        traceback.print_stack(file=sys.stdout)
        return False

class RMItem:
    ''' Repository Item - collects items which can be be stored in multiple versions into 
    one object. e.g. contrib/Contents-amd64.gz and contrib/Contents-amd64 are the same RMItem
    but will have one file entry for each of them'''

    def __init__(self, name, f=None):
        ''' Create a entry with given optional file entry'''
        self.name = name
        if f:
            self.items = [f]
        else:
            self.items = []
        self.present = None # package item that is present
        global debug
        if debug > 1:
            print("RMItem(name=%s, f=%s) created" % (name, repr(f)))

    def add(self, f):
        self.items.append(f)
        global debug
        if debug > 1:
            print("RMItem(name=%s) add %s" % (self.name, repr(f)))

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
        self.allPackages = True

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
        d = setup.get('repository', None)
        if d:
            print("Mirroring repository %s" % d)
        else:
            d = RepositoryMirror.repository
        print("Using default repository URL %s" % d)
        RepositoryMirror.repository = d
        d = setup.get('distributions', None)
        if d:
            RepositoryMirror.distributions = d.split()
        d = setup.get('components', None)
        if d:
            RepositoryMirror.components = d.split()
        d = setup.get('architectures', None)
        if d:
            RepositoryMirror.architectures = d.split()
        d = setup.get('options', None)
        if d:
            RepositoryMirror.cfg_options = d.split()
        else:
            RepositoryMirror.cfg_options = None
        RepositoryMirror.tdir = setup.get('tdir', RepositoryMirror.tdir)
        RepositoryMirror.lmirror = setup.get('lmirror', RepositoryMirror.lmirror)
        pL = {}
        for d in RepositoryMirror.distributions:
            print("Checking distribution '", d, " : 'packages-'" + d, "'", sep='')
            pkglist = setup.get('packages-' + d, None)
            if pkglist:
                print("  ** Restricted with pkglist: ", pkglist, " **")
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
        pkg.modified = False
        if debug >= 1:
            print('checkRelEntryFile(rel=%s comp=%s arch=%s size=%s, hash(%s)=%s)'
                % (rel.name, pkg.comp, pkg.arch, pkg.size, rel.hashtype, pkg.hash))
        path = self.getPackagePath(rel.name, pkg)
        url = self.getPackageURL(rel.name, pkg)
        pkg.cfile = cfile = CacheFile(url, ofile=path)
        if check_hash:
            hash = pkg.hash
        else:
            hash = None
        if not cfile.check(size=pkg.size, hash=hash, type=rel.hashtype):
            if verbose:
                print("checkRelEntryFile(path=%s url=%s) - Missing or not matching" % (path, url))
            if update:
                if cfile.fetch():
                    pfile = cfile.tfile
                    if checkFile(pfile, size=pkg.size, hash=hash, type=rel.hashtype):
                        pkg.missing = False
                        pkg.modified = True
                        cfile.update()
                        pfile = cfile.ofile
                        print("checkRelEntryFile file %s updated" % pkg.name)
                    else:
                        print("checkRelEntryFile updated file %s doesn't match" % pkg.name)
                        pkg.missing = True
                else:
                    pkg.missing = True
                    if verbose:
                        print("checkRelEntryFile: Fetching url=%s failed" % url)
            else:
                pkg.missing = True
        else:
            if verbose:
                print("checkRelEntryFile(path=%s url=%s) - ok" % (path, url))
            pfile = cfile.ofile
            pkg.missing = False

        if pkg.missing:
            print(' Warning: %s - Release Entry file %s missing' % (rel.name, pname))
            if verbose:
                print("Release entry file (path=%s url=%s) - missing" % (path, url))
        return pkg

    def checkPackage(self, rel, pkg, update=True):
        '''
        Check the Package file pkg on the local mirror and it's debian packages
        '''

        #pkg = rel.pkgFiles[pname]
        if verbose:
            print('checkPackage(pkg=%s rel=%s comp=%s arch=%s size=%s, hash(%s)=%s)'
                % (pkg.name, rel.name, pkg.comp, pkg.arch, pkg.size, rel.hashtype, pkg.hash))
        path = self.getPackagePath(rel.name, pkg)
        url = self.getPackageURL(rel.name, pkg)
        pkg.cfile = cfile = CacheFile(url, ofile=path)
        pkg.modified = True # Assume worse case
        if check_hash:
            hash = pkg.hash
        else:
            hash = None
        if not cfile.check(size=pkg.size, hash=hash, type=rel.hashtype):
            if update:
                try:
                    if not cfile.fetch():
                        pkg.missing = True
                        return pkg
                    pfile = cfile.tfile
                    pkg.modified = True
                    pkg.missing = True
                    if checkFile(pfile, size=pkg.size, hash=hash, type=rel.hashtype):
                        pkg.missing = False
                        cfile.update()
                        pfile = cfile.ofile
                        print("Package file: %s updated" % pkg.name)
                    elif os.path.exists(cfile.ofile):
                        print("Package file: %s missing" % pkg.name)
                    else:
                        print("Package file %s doesn't match" % pkg.name)
                except Exception as e:
                    pkg.missing = True
                    print("Exception %s " % repr(e))
                    import traceback, sys
                    traceback.print_stack(file=sys.stdout)

            else:
                pkg.missing = True
        else:
            if verbose:
                print("checkPackage(path=%s url=%s) - ok" % (path, url))
            pfile = cfile.ofile
            pkg.modified = False
            pkg.missing = False

        if verbose:
            if pkg.missing:
                print(" Warning missing package file %s url=%s" % (path, url))
            return pkg
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
        if debug > 0:
            print("checkState(%s, update=%s)" % (repr(self), str(update)))
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
            o_missing = [] # Missing other entries
            if not r.present:
                print('Skipping Release %s as Release file %s is missing' % (r.name, r.cfile.ofile))
                continue
            if args.verbose:
                print('Examining release file %s (%s)' % (r.name, r.cfile.ofile))
            for i in r.pkgItems.values():
                if args.verbose:
                    print('Examining Package %s ' % (i.name))
                r.checkPackageItem(i, update)
                if debug > 2:
                    print('Package %s - %d entries' % (i.name, len(i.items)))
            missing += r.total_missing
            self.cnt += r.deb_missing
            for o in r.otherFiles:
                if args.verbose:
                    print('Examining other file %s ' % (o))
                pkg = self.checkRelEntryFile(r, o, update)
                if pkg.missing:
                    self.updated = True
                    self.missing = True
                    o_missing.append(pkg)
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
            if len(o_missing) > 0:
                print("%d missing other files - check for compressed versions"
                    % len(o_missing))
                for p in o_missing:
                    suf = '.xz'
                    f = p.cfile.ofile + suf
                    if os.access(f, os.F_OK):
                        print("Found %s - attempting to uncompress it" % f)
                        if subprocess.call(["unxz", "-k", "-f", f]):
                            print("  ** failed to unxz'ed file %s" % f)
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
        cRelFile.validate(update)
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
        if not cfile.fetch():
            print("%s Unable to fetch Release file - using old one" % dist)
            return oRelFile
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
   rItems - dict of entries index'ed by file name with suffix removed
   deb_missing - deb files missing
   total_missing - total bytes of missing files
    '''

    def __init__(self, rep, name, rfile, sig_cfile):
        ''' Reads in a Release from given path name
        rep - Repository Mirror
        name - Distribution/Release Name
        rfile - full path to Release file
        info - dict of Release file fields (indexed by field)
        pkgItems - dict of RMItem
        '''

        self.repMirror = rep
        self.rfile = rfile
        self.name = name
        self.sig = sig_cfile
        self.info = {}
        self.pkgItems = {}
        self.pkgFiles = {}
        self.otherFiles = {}
        self.changed = False
        self.present = False
        self.hashtype = 'MD5Sum'
        self.deb_missing = 0
        self.total_missing = 0
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
            if len(w) <= 0: continue
            if w[0] in { 'MD5Sum:', 'SHA1:', 'SHA256:' }:
                hash = w[0][0:-1]
                self.hashtype = hash
                break
            if w[0][-1] == ':':
                self.info[w[0][0:-1]] = ' '.join(w[1:])
                continue
            print("RelFile: %s Ignoring strange word %s" % (rfile, w[0]))

        if verbose:
            print(self.name, " - Hash is type ", self.hashtype)
        for l in fp:
            l = l.lstrip().rstrip()
            w = l.split()
            if len(w) <= 0: continue
            if w[0] in { 'MD5Sum:', 'SHA1:', 'SHA256:' }:
                #hash = w[0][0:-1]
                #self.hashtype = hash
                #print("#2 self.hashtype=", hash)
                print("skipping - other hashes: ", w[0][0:-1])
                break
            if len(w) > 2 and 'Packages' in w[2]:
                if int(w[1]) == 0:
                    continue
                f = w[2]
                (comp, arch, ctype) = PkgFile.parsePfile(f)
                if comp not in RepositoryMirror.components:
                    continue
                if arch not in RepositoryMirror.architectures:
                    continue
                if f.endswith('Packages.diff/Index'):
                    if args.verbose:
                        print('Skipping diff index: ', f)
                    continue
                pf = PkgFile(rep, f, hash=w[0], size=int(w[1]), relfile=self)
                nlist = f.split('.')
                n = nlist[0]
                if n in self.pkgItems:
                    item = self.pkgItems[n]
                    item.add(pf)
                else:
                    item = RMItem(n, pf)
                    self.pkgItems[n] = item
                #if ctype == 'gzip':
                #self.pkgFiles[f] = PkgFile(rep, f, hash=w[0], size=w[1], relfile=self)
                if verbose:
                    print("Tracking package file %s (size %d)" % (f, int(w[1])))
                continue
            if len(w) > 2 and 'Translation' in w[2]:
                if int(w[1]) == 0:
                    continue
                f = w[2]
                (comp, arch, bzctype) = PkgFile.parsePfile(f)
                if comp in RepositoryMirror.components \
                    and arch == 'Translation' and (f.endswith('-en')
                        or f.endswith('-en.bz2') or f.endswith('-en.xz')):
                    self.otherFiles[f] = PkgFile(rep, f, hash=w[0], size=int(w[1]), relfile=self)
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
                    self.otherFiles[f] = PkgFile(rep, f, hash=w[0], size=w[1], relfile=self)
                    if verbose:
                        print("Grab component %s" % (comp))
                continue
            if len(w) > 2 and 'Contents-' in w[2]:
                continue
            if len(w) > 2 and 'Sources' in w[2]:
                continue
            if extra_verbose:
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
        global debug
        if debug > 2:
            print("RelFile(%s rfile=%s hashtype=%s %d pkgItems %d pkgFiles %d otherFiles)" % (
                self.name, self.rfile, self.hashtype, len(self.pkgItems),
                len(self.pkgFiles), len(self.otherFiles)))

    def validate(self, update=True):
        ''' Check if items in Release file are present and correct'''
        global args
        rep = self.repMirror
        for relfile_item in self.pkgItems.values():
            for pkg in relfile_item.items:
                path = rep.getPackagePath(self.name, pkg)
                if not os.path.exists(path):
                    if not args.quiet:
                        print(" file: %s missing" % pkg.name)
                    pkg.missing = True
                    continue
                if check_hash:
                    hash = pkg.hash
                else:
                    hash = None
                if not checkFile(path, size=pkg.size, hash=hash, type=self.hashtype):
                    if update and not args.dry_run:
                        print(" removing file %s doesn't match Release file" % path)
                        os.unlink(path);
                    else:
                        print(" file %s doesn't match Release file" % path)

    def checkPackageItem(self, pi, update):
        ''' Check through all listed items and compare with files present
        If update synchronise the files so at least one file is present
        obsolete files are removed. If not updating just compute what deletes/updates
        and needed to synchronise'''
        # Search through items to find first any present
        if debug > 0:
            print("checkPackageItem(%s, pi=%s, update=%s)" %
                (repr(self), repr(pi), str(update)))
        rep = self.repMirror
        for pkg in pi.items:
            if rep.allPackages:
                rep.checkPackage(self, pkg, update)
                if pkg.modified:
                    rep.updated = True
                if pkg.missing:
                   continue
                pi.present = pkg
                if verbose:
                    print("processing Package file %s" % pi.name)
                pkg.rdPkgFile(pkg.cfile.ofile)
                if pkg.cnt > 0:
                    print(pi.name, " missing ", pkg.cnt)
                self.deb_missing += pkg.cnt
                self.total_missing += pkg.total_missing
            elif pi.present:
                rep.checkPackage(self, pkg, False)
            else:
                rep.checkPackage(self, pkg, update)
                if pkg.modified:
                    rep.updated = True
                if not pkg.missing:
                    pi.present = pkg
                    break
        if rep.allPackages:
            return
        if not pi.present:
            return
        if verbose:
            print("processing Package file %s" % pi.name)
        pkg.rdPkgFile(pkg.cfile.ofile)
        if pkg.cnt > 0:
            print(pi.name, " missing ", pkg.cnt)
        self.deb_missing += pkg.cnt
        self.total_missing += pkg.total_missing

    def __repr__(self):
        return 'RelFile({!r}, {!r}, {!r}, {!r})'.format(self.repMirror, self.name, self.rfile, self.sig)

    def __str__(self):
        return 'RelFile()\n name: {!s}\n file: {!s}\n'.format(self.name, self.rfile) + \
            ' Suite: {!s}\n Codename: {!s}\n Version: {!s}\n Date: {!s}\n'.format(self.suite, self.codename, self.version, self.date) + \
            ' Components: {!r}\n Architectures: {!r}\n Description: {!s}'.format(self.components, self.archs, self.desc)

#Note: Can have two packages with same name but different architecture.
# e.g. linux-source-3.16 amd64 + all
class PkgEntry():
    ''' Package file entry - usually detailing a .deb file '''
    def __init__(self, name, arch, fname, hash, hashtype, size):
        ''' Package file entry defining a .deb file '''
        self.name = name
        self.arch = arch
        self.fname = fname
        self.hash = hash
        self.hashtype = hashtype
        self.size = size
        global debug
        if debug > 2:
            print("PkgEntry(%s fname=%s hashtype=%s size=%s)" %
                (name, fname, hashtype, size))

    def getPkgEntry(fp):
        '''Return a Package Entry or None from Package file fp'''
        try:
            p = PkgEntry.rdPkgDetails(fp)
            if len(p) == 0:
                    return None

            #print("getPkgEntry() = %s" % repr(p))
# Warning: a binary-<arch>/Packages file can contain all architecture entries!
# This confused me to think perhaps we can have two packages with same name but
# different architectures!  # e.g. linux-source-3.16 - amd64 and all
# But not necessarily...
            n = p['Package']
            a = p['Architecture']
            if check_hash:
                if 'MD5sum' in p:
                    return PkgEntry(n, a, p['Filename'], p['MD5sum'], 'MD5Sum', p['Size'])
                elif 'SHA256' in p:
                    return PkgEntry(n, a, p['Filename'], p['SHA256'], 'SHA256', p['Size'])
                else:
                    raise Exception
            return PkgEntry(n, a, p['Filename'], None, 'MD5Sum', p['Size'])

        except OSError as e:
            print('getPkgEntry() failed: %s' % e.strerror)
            return None

    def rdPkgDetails(fp):
        '''read one Package file entry from fp into a Dict of key/values'''

        p = {}
        k, v = None, ''
        for l in fp:
            #l = l.decode()
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
    def __init__(self, rep, name, hash=0, size=0, relfile=None):
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
        self.hash = hash
        self.size = int(size)
        p = PkgFile.parsePfile(name)
        self.comp, self.arch = p[0], p[1]
        self.ignored = 0
        global debug
        if debug > 2:
            print("PkgFile(%s ctype=%s size=%s)" % (name, ctype, size))

    def rdPkgFile(self, rfile):
        '''
        Read in from a Package file, update state of .deb files
          - Restricted by any pkglist associated with that release
        '''

        global args
        if debug > 0:
            print("rdPkgFile(%s, rfile=%s)" % (repr(self), str(rfile)))
        self.total_missing = 0
        if self.ctype.endswith('lzma'):
            print("Package file ", rfile, " is xz'ed - unxzing")
            if rfile.endswith('.xz'):
                plain = rfile[:-3]
            else:
                plain = rfile + ".txt"
                print(" Saving unxz-ed file to ", plain )
            if subprocess.call(["unxz", "-k", "-f", rfile]):
                print("  *** ", rfile, ": failed to unxz'ed  ***")
                return False
            fp = open(plain)
        elif self.ctype.endswith('bz2'):
            fp = bz2.open(rfile, 'rt')
        elif self.ctype.endswith('gzip'):
            fp = gzip.open(rfile, 'rt')
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
            if p.arch != self.arch and not args.any_arch_pf :
                if args.extra_verbose:
                    print("Skipping %s unexpected architecture '%s' in %s package file"
                        % (p.name, p.arch, self.arch))
                continue
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
                print("rdPkgFile() Want ", p.name, " arch=", p.arch, " ofile=", f)
            cfile = CacheFile(u, ofile=f)
            if args.onlypkgs:
                hash = None
            else:
                hash = p.hash
            #print("check", p.name, "hash=", str(hash), "type=", self.relfile.hashtype)
            if not cfile.check(size=s, hash=hash, type=self.relfile.hashtype):
                p.missing = True
                p.cfile = cfile
                self.total_missing += s
                self.cnt += 1
                if args.verbose or self.cnt < 5:
                    print(' Missing %s  size %d, hash(%s)=%s' % (fn, s, p.hashtype, p.hash))
            else:
                p.missing = False
            # May have multiple versions of the same debian package in the one release!
            self.pkgs[p.fname] = p
            self.pkgfiles[p.fname] = p

        fp.close()
        if not args.verbose and self.cnt >= 5:
            print(' .... Total %d missing debs' % self.cnt)
        if self.total_missing > 0:
            if  self.total_missing < 1024*1024:
                sz_str = "%d bytes" % self.total_missing
            elif  self.total_missing < 1024*1024*1024:
                sz_str = "%dMb" % (self.total_missing/(1024*1024))
            else:
                sz_str = "%dGb" % (self.total_missing/(1024*1024*1024))
            print("Package %s Total %d Ignored %d Examined %d Missing %d debs %s"
                % (self.name, self.total, self.ignored, len(self.pkgs), self.cnt, sz_str))
        else:
            if not args.quiet or self.ignored != 0:
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
                ctype = 'xz'
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
        self.fetched = False
        self.updated = False

    def fetch(self, tfile=None):
        ''' fetch a fresh copy of the file into tfile '''

        global args, debug

        if self.fetched:
            return True
        try:
            if args.dry_run:
                if args.verbose:
                    print("Dry-Run Skip Fetching %s" % self.url)
                return False
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
            req = urllib.request.Request(self.url)
            if req.type == 'file':
                of.close()
                if args.uselinks:
                    #if args.verbose:
                    #    print("os.link(%s, %s)" % (req.selector, self.tfile))
                    if os.access(self.tfile, os.F_OK):
                        os.unlink(self.tfile)
                    os.link(req.selector, self.tfile)
                    self.fetched = True
                    if debug >= 2:
                        print("Fetched %s -> %s" % (self.url, self.tfile))
                    return True
                #if args.verbose:
                #    print("shutil.copy(%s, %s)" % (req.selector, self.tfile))
                # Fix Problem with tfile being readonly
                os.chmod(self.tfile, stat.S_IRUSR|stat.S_IWUSR|stat.S_IRGRP|stat.S_IROTH)
                shutil.copy(req.selector, self.tfile)
                self.fetched = True
                if debug >= 2:
                    print("Fetched %s -> %s" % (self.url, self.tfile))
                return True
            uf = urllib.request.urlopen(self.url)
            content_type = uf.getheader('Content-Type')
            if debug >= 2:
                print("Response.Content-Type", repr(uf.getheader('Content-Type')))

            while True:
                b = uf.read(CacheFile.BUFSIZE)
                if not b: break
                of.write(b)

            uf.close()
            of.close()
            self.fetched = True
            url = str(self.url)
            if debug >= 2:
                print("content-type=", content_type, " url=", url)
                print("tfile=", self.tfile)
            if content_type == None:
                pass
            elif content_type.endswith("x-gzip") and not url.endswith(".gz"):
                print("File sent gzipped - gunzipping")
                gzf = self.tfile + ".gz"
                if debug >= 2:
                    print("rename %s -> %s" % (self.tfile, gzf))
                os.rename(self.tfile, gzf)
                if subprocess.call(["gunzip", "-k", "-f", gzf]):
                    print(self.url, ": returned bad gzipp'ed file ", gzf)
                    return False
            elif content_type.endswith("x-bzip2") and not url.endswith(".bz2"):
                print("File sent bzip2'ed - bunzipping")
                bzf = self.tfile + ".bz2"
                if debug >= 2:
                    print("rename %s -> %s" % (self.tfile, bzf))
                os.rename(self.tfile, bzf)
                if subprocess.call(["bunzip2", "-k", "-f", bzf]):
                    print(self.url, ": returned bad bzipp'ed file ", bzf)
            elif content_type.endswith("x-xz") and not url.endswith(".xz"):
                print("File sent xz'ed - unxzing")
                bzf = self.tfile + ".xz"
                os.rename(self.tfile, bzf)
                if subprocess.call(["unxz", "-k", "-f", bzf]):
                    print(self.url, ": returned bad xz'ed file ", bzf)
                    return False
            elif content_type.endswith("application/x-debian-package") and url.endswith(".deb"):
                print("File sent x-debian-package .deb - Ok")
            elif content_type.endswith("application/vnd.debian.binary-package") and url.endswith(".deb"):
                print("File sent vnd.debian.binary-package .deb - Ok")
            elif content_type.endswith("application/octet-stream"):
                print("File application/octet-stream sent - ok")
            elif content_type.endswith("application/x-xz"):
                print("File application/x-xz sent - ok")
            elif content_type.endswith("application/x-gzip"):
                print("File application/x-gzip sent - ok")
            elif content_type.endswith("application/x-bzip2"):
                print("File application/bzip2 sent - ok")
            else:
                print("Unsupported content-type: ", content_type)
                return False

            if debug >= 2:
                print("Fetched %s -> %s" % (self.url, self.tfile))
            return True

        except urllib.error.HTTPError as e:
            if not args.verbose:
                if e.code == 404:
                    return False
            print(self.url, ":", str(e))
            return False

        except OSError as e:
            if not args.verbose:
                if e.errno == errno.ENOENT:
                    return False
            print("OSError: ", str(e))
            return False

        except Exception as e:
            print("Exception: ", tfile, ",", str(e))
            return False

    def check(self, size=None, hash=None, type=None):
        '''
        Return True if the cached file is present and matches given size and md5sum if not None
        '''
        return checkFile(self.ofile, size=size, hash=hash, type=type)

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
        if self.updated:
            return True
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
            self.updated = True
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

        print("Reading Release file %s : %d Package files" % (r, len(rf.pkgItems)))

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
    parser.add_argument('-Q', dest='quiet', action='store_true',
        help='quiet mode')
    parser.add_argument('-e', dest='extra_verbose', action='store_true',
        help='extra verbose mode')
    parser.add_argument('-run_tests', dest='run_tests', action='store_true',
        help='Run unit tests')
    parser.add_argument('-create', dest='create', action='store_true',
        help='Create Repository if missing')
    parser.add_argument('-fetch', dest='fetch', action='store_true',
        help='fetch missing packages')
    parser.add_argument('-one-package-file', dest='onePackageFile', action='store_true',
        help='fetch all package files (gzipped, ...)')
    parser.add_argument('-uselinks', dest='uselinks', action='store_true',
        help='URLs are local files - use links to save space')
    parser.add_argument('-norefresh', dest='update', action='store_false',
        help='do not refresh status from original repository')
    parser.add_argument('-T', '--Timeout', dest='timeout', default=None,
        help='give up after this many seconds|mins|hours|days - N[smhd] ')
    parser.add_argument('-only-pkgs-size', dest='onlypkgs', action='store_true',
        default=False, help='only check package file size')
    parser.add_argument('-any-arch-in-package-files', dest='any_arch_pf',
        action='store_true', default=False,
        help='only accept <arch> packages binary-<arch> file - i.e. <all> entries skipped')

    args = parser.parse_args()
    verbose, dry_run, very_dry_run  = args.verbose, args.dry_run, args.very_dry_run
    extra_verbose = args.extra_verbose

    if args.onlypkgs:
        check_hash = False
        if verbose:
            print("check_hash=", str(check_hash))

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
    if RepositoryMirror.cfg_options:
        if verbose: print(" Adding options from configuration file:\n  ",
            RepositoryMirror.cfg_options)
        args = parser.parse_args(RepositoryMirror.cfg_options, namespace=args)
    repM = RepositoryMirror()

    if args.info:
        repM.dump_info()
        repM.cleanUp()

    if args.onePackageFile:
        repM.allPackages = False
    nfails = 0
    if repM.skeletonCheck(args.create) != True:
        print("Unable to set up repository mirror for %s at %s"
            % (repM.repository, repM.lmirror))
        sys.exit(1)
    if repM.checkState(args.update) == False and repM.cnt == 0:
# For all the release files present read, possibly update
# For all the packages file present in a release - read and possibly update
# For all the .deb (packages) listed check if present and correct size/checksums
        for r in repM.relfiles.values():
            if r.present:
                print("Release %s - missing %d" % (r, r.deb_missing))
                repM.cnt += r.deb_missing
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
                print("%d package files:" % len(r.pkgItems))
            for pi in r.pkgItems.values():
                if args.timeout and gettime() >= args.timeout:
                    print("Time out expired skipping Package", pi.name," ...")
                    break
                if args.verbose:
                    print("Checking package %s for missing debs" % (pi.name))
                if not pi.present:
                    print("  Skip missing package %s" % (pi.name))
                    continue
                p = pi.present
                for d in p.pkgs.values():
                    if args.timeout and gettime() >= args.timeout:
                        print("  Time out expired skipping deb " + d.name + " ...")
                        break
                    p.total_fetched = 0
                    p.last_report = p.fetch_start = gettime()
                    if d.missing:
                        print("  Fetching %s - size %s" % (d.name, d.size))
                        try:
                            start = gettime()
                            if not d.cfile.fetch():
                                print("  Failed to fetch %s - skipping\n" % d.fname)
                                nfails += 1
                                continue
                            d.cfile.update()
                            elapsed = gettime() - start
                            p.total_fetched += int(d.size)
                            if start - p.last_report > repM.report_time:
                                av_speed = p.total_fetched/(start - p.fetch_start)
                                print("  %s %s %s %3.1f % fetched Estimating %d seconds to complete" %
                                    (p.name, p.arch, p.comp, 100*p.total_fetched/p.total_missing, (p.total_missing - p.total_fetched)/av_speed) )
                            elif elapsed > min_time:
                                speed = (8*int(d.size)/elapsed)/1000.
                                if speed < 2000.0:
                                    print("  Downloaded in %.1f seconds = %.3f kbit/s" % (elapsed, speed))
                                elif speed < 2000000.0:
                                    print("  Downloaded in %.3f seconds = %.3f Mbit/s" % (elapsed, speed/1000.))
                                else:
                                    print("  Downloaded in %.6f seconds = %.3f Gbit/s" % (elapsed, speed/1000000.))

                        except OSError:
                            print("  Failed to fetch %s" % d.fname)
                            nfails += 1

    if nfails == 0:
        repM.cleanUp(0)
    repM.cleanUp(1)
    if args.timeout and gettime() >= args.timeout:
        print("Timed out expired - incomplete download");
