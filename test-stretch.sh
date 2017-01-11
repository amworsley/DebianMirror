#! /bin/sh

die() {
ST=${2:-"1"}
MSG=${1:-"Exiting with status $ST"}
    echo $MSG
    exit $ST
}

TDIR="tmp"
TOPDIR="$(pwd)"
PATH=$PATH:$TOPDIR

mkdir $TDIR || die "Unable to make directory $TDIR"

cd $TDIR

RM_CFG="stretch-mirror.cfg"

echo "Creating $RM_CFG"
cat >$RM_CFG <<EOF
# to end of line is a comment
# Place all settings in 'setup' section header :
[setup]
# Rest of lines are <Parameter> ':' <Value>
# e.g. define URL for the repository to mirror:
repository: http://ftp.debian.org/debian
#repository: file://$TOPDIR/jessie-test/jessie-mirror
# Restrict to given space seperated list of releases (distributions) to mirror:
distributions: stretch
# Name local directory to place mirror into:
lmirror: stretch-mirror
# Restrict debs to mirror for Release wheezy/updates to those in pkg.list
packages-stretch: pkg-5.list
EOF

echo "Creating pkg-5.list"
cat >pkg-5.list <<EOF
xserver-xorg-input-vmmouse
module-assistant
python-pymtp
tcpd
gocr
sane-utils
hwdata
libio-stringy-perl
libhttp-date-perl
debconf
exim4-config
EOF

echo "Create repository $RM_CFG"
RepositoryMirror.py -c $RM_CFG -create

echo "Dumping out info"
RepositoryMirror.py -c $RM_CFG -info

echo "Printing out download summary"
RepositoryMirror.py -c $RM_CFG

echo "Downloading packages"
RepositoryMirror.py -c $RM_CFG -fetch
