#! /bin/bash

# Simple fast release update testing

rm azza-updates-50/dists/wheezy/updates/Release
./RepositoryMirror.py -c azza-50.cfg -norefresh \
    | grep 'Warning: wheezy/updates - Release file missing'
./RepositoryMirror.py -c azza-50.cfg
if [ -e azza-updates-50/dists/wheezy/updates/Release ]; then 
    echo "Updated Release file - ok"
else
    echo "Release file - not updated"
    exit 1
fi

if ./RepositoryMirror.py -c azza-50.cfg -norefresh \
  | grep 'azza-updates-50 is up to date'; then
    echo "Release up to date - ok"
else
    echo "Release not up to date - fail"
    exit 2
fi
    
