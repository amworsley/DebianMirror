#! /bin/sh

# Directory of RepositoryMirror 
RM=/movies3/deb-mirror/
# Path to RepositoryMirror.py script
RMPATH=/usr/local/bin

cd $RM
$RMPATH/RepositoryMirror.py -fetch
$RMPATH/RepositoryMirror.py -fetch -c jessie.cfg
$RMPATH/RepositoryMirror.py -fetch -c stretch.cfg
$RMPATH/RepositoryMirror.py -c stretch-updates.cfg  -fetch
$RMPATH/RepositoryMirror.py -c jessie-updates.cfg  -fetch
