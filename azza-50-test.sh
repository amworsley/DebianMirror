#! /bin/bash

# Simple fast release update testing

check_norefresh() {
    EXP_OUTPUT=${1:-"azza-updates-50 is up to date"}
    ARG1=${2:-"-norefresh"}
    if ./RepositoryMirror.py -c azza-50.cfg $ARG1 \
      | grep "$EXP_OUTPUT"; then
        echo "$EXP_OUTPUT - ok"
    else
        echo "check_norefresh() expected $EXP_OUTPUT - fail"
        exit 2
    fi
}
check_uptodate() {
    if ./RepositoryMirror.py -c azza-50.cfg -norefresh \
      | grep 'azza-updates-50 is up to date'; then
        echo "Release up to date - ok"
    else
        echo "Release not up to date - fail"
        exit 2
    fi
}

rm azza-updates-50/dists/wheezy/updates/Release

check_norefresh 'Warning: wheezy/updates - Release file missing' 
#./RepositoryMirror.py -c azza-50.cfg -norefresh \
    #| grep 'Warning: wheezy/updates - Release file missing'
#check_norefresh 'file:azza-updates: 1 release changed' '' 
./RepositoryMirror.py -c azza-50.cfg
if [ -e azza-updates-50/dists/wheezy/updates/Release ]; then 
    echo "Updated Release file - ok"
else
    echo "Release file - not updated"
    exit 1
fi
check_uptodate

echo 
echo "Testing Missing Package file"
rm azza-updates-50/dists/wheezy/updates/contrib/binary-amd64/Packages.bz2

check_norefresh 'Warning: wheezy/updates - package file contrib/binary-amd64/Packages.bz2 missing' 

if [ -e azza-updates-50/dists/wheezy/updates/contrib/binary-amd64/Packages.bz2 ]; then 
    echo "Package file was refreshed - -norefresh option not working..."
    exit 1
else
    echo "Package file is not updated : -norefresh option working..."
fi

./RepositoryMirror.py -c azza-50.cfg
if [ -e azza-updates-50/dists/wheezy/updates/contrib/binary-amd64/Packages.bz2 ]; then 
    echo "Package file was refreshed - correctly"
else
    echo "Package file was not updated by ./RepositoryMirror.py -c azza-50.cfg"
    exit 1
fi

check_uptodate
