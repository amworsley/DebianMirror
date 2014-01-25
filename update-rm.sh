#! /bin/sh

# Use RepositoryMirror to update mirrors
RM=/movies3/work/RM
PATH=$PATH:/usr/local/bin

cd $RM
RepositoryMirror.py -v -fetch
