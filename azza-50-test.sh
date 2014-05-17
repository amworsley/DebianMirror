#! /bin/bash

# print out useful message and optional stack trace and then ext
die() {
    MSG=${1:-"exiting"}
    ST=${2:-"1"}
    echo "die() :$MSG - exiting $ST"
    I=1
    while [ ${FUNCNAME[$I]} ]; do
	echo "$I: ${FUNCNAME[$I]}()"
	I=$(($I+1))
    done
    exit $ST
}

# Simple fast release update testing

# check RepositoryMirror.py -c azza-50.cfg $ARG produces
# expected output EXP_OUTPUT and if not does an exit 2
check_RM() {
    EXP_OUTPUT=${1:-"azza-updates-50 is up to date"}
    ARG1=${2:-"-norefresh"}
    if ./RepositoryMirror.py -c azza-50.cfg $ARG1 \
      | grep "$EXP_OUTPUT"; then
        echo "$EXP_OUTPUT - ok"
    else
        die "check_RM() expected $EXP_OUTPUT - fail" 2
        exit 2
    fi
}
# Check that a norefresh produces given message
check_norefresh() {
    check_RM "$1" "$2"
}
check_uptodate() {
    if ./RepositoryMirror.py -c azza-50.cfg -norefresh \
      | grep 'azza-updates-50 is up to date'; then
        echo "Release up to date - ok"
    else
        die "Release not up to date - fail" 3
        exit 2
    fi
}

testBG() {
    TESTN=${1:-"Test"}
    TESTNUM=$(($TESTNUM+1))
    echo " *** Test $TESTNUM: $TESTN **** "
}

testEND() {
    ARG1=${1:-"Passed"}
    echo "### End Test $TESTNUM: $ARG1 ### "
    echo ""
}
check_missing_release () {
    testBG "detection of missing Release file"
    rm azza-updates-50/dists/wheezy/updates/Release
    check_norefresh 'Warning: wheezy/updates - Release file missing' 
    ./RepositoryMirror.py -c azza-50.cfg
    if [ -e azza-updates-50/dists/wheezy/updates/Release ]; then 
	echo "Updated Release file - ok"
    else
	die "Release file - not updated"
    fi
    check_uptodate
    testEND
}

testFullUpdate() {
    testBG "Full update"
    echo "First bring repository completely up to date"
    if ! ./RepositoryMirror.py -c azza-50.cfg -fetch; then
	die "Unable to do full update for azza-50.cfg"
    fi
    check_uptodate
    testEND
}

testFullUpdate
check_missing_release

testBG "Testing Missing Package file"
rm azza-updates-50/dists/wheezy/updates/contrib/binary-amd64/Packages.bz2

check_norefresh 'Warning: wheezy/updates - package file contrib/binary-amd64/Packages.bz2 missing' 

if [ -e azza-updates-50/dists/wheezy/updates/contrib/binary-amd64/Packages.bz2 ]; then 
    echo "Package file was refreshed - -norefresh option not working..."
    echo $FUNCNAME
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
testEND

testBG "Missing .deb file"
DFILE='azza-updates-50/pool/updates/main/x/xorg-server/xserver-common_1.12.4-6+deb7u2_all.deb'
rm -f $DFILE

./RepositoryMirror.py -c azza-50.cfg
if [ -e $DFILE ]; then
    echo "./RepositoryMirror.py incorrectly fetched missing .deb file $(basename $DFILE) - FAIL"
    exit 1
else
    echo "./RepositoryMirror.py correctly refused to fetch missing .deb file $(basename $DFILE)"
fi

./RepositoryMirror.py -c azza-50.cfg -fetch
if [ -e $DFILE ]; then
    echo "./RepositoryMirror.py correctly refreshes missing .deb file $(basename $DFILE)"
else
    echo "./RepositoryMirror.py did not fetch missing .deb file $(basename $DFILE) - FAIL"
    exit 1
fi
check_uptodate
testEND

testBG "Corrupt file $(basename $DFILE) - check if this is detected"
echo "Blah Blah" >> $DFILE
check_RM "Repository 2 changes" ""
./RepositoryMirror.py -c azza-50.cfg -fetch
check_uptodate
testEND

