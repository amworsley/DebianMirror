#! /bin/sh

# Directory of RepositoryMirror 
RM=/movies3/deb-mirror/
# Path to RepositoryMirror.py script
RMPATH=/usr/local/bin

cd $RM
# Old stable
#$RMPATH/RepositoryMirror.py -fetch
#$RMPATH/RepositoryMirror.py -fetch -c jessie.cfg
#$RMPATH/RepositoryMirror.py -c jessie-updates.cfg  -fetch
#$RMPATH/RepositoryMirror.py -c jessie-updates-security.cfg  -fetch
# stable
$RMPATH/RepositoryMirror.py -fetch -c stretch.cfg
$RMPATH/RepositoryMirror.py -c stretch-updates.cfg  -fetch
$RMPATH/RepositoryMirror.py -c stretch-updates-security.cfg  -fetch
# testing
$RMPATH/RepositoryMirror.py -c buster.cfg  -fetch
$RMPATH/RepositoryMirror.py -c buster-updates.cfg  -fetch
$RMPATH/RepositoryMirror.py -c buster-updates-security.cfg  -fetch
