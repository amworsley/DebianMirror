#! /bin/sh

# Directory of RepositoryMirror 
RM=/movies3/deb-mirror/
# Path to RepositoryMirror.py script
RMPATH=/usr/local/bin

cd $RM
$RMPATH/RepositoryMirror.py -v -fetch
$RMPATH/RepositoryMirror.py -v -fetch -c jessie.cfg
$RMPATH/RepositoryMirror.py -v -fetch -c stretch.cfg
