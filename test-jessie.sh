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

RM_CFG="jessie-mirror.cfg"

echo "Creating $RM_CFG"
cat >$RM_CFG <<EOF
# to end of line is a comment
# Place all settings in 'setup' section header :
[setup]
# Rest of lines are <Parameter> ':' <Value>
# e.g. define URL for the repository to mirror:
repository: file://$TOPDIR/jessie-test/jessie-mirror
# Restrict to given space seperated list of releases (distributions) to mirror:
distributions: jessie
# Name local directory to place mirror into:
lmirror: jessie-mirror
# Restrict debs to mirror for Release wheezy/updates to those in pkg.list
packages-jessie: pkg-50.list
EOF

echo "Creating pkg-50.list"
cat >pkg-50.list <<EOF
xserver-xorg-input-vmmouse
libexempi3
libkfile4
module-assistant
python-pymtp
libgtkspell0
python-pkg-resources
tcpd
libmail-imapclient-perl
libmlt0.2.3
python-twisted-conch
libbsf-java
libslf4j-java
libmozjs1d
libbonoboui2-0
linux-source
libplexus-sec-dispatcher-java
gocr
libfftw3-3
libtext-wrapi18n-perl
libclutter-1.0-0
sane-utils
libgpod-common
libustr-1.0-1
fonts-freefont-ttf
java-common
hwdata
libantlr-java
djvulibre-desktop
libgssdp-1.0-2
libjson-glib-1.0-0
libaudio-wav-perl
libbluray1
libgssdp-1.0-3
libio-stringy-perl
libhttp-date-perl
gir1.2-gee-1.0
debconf
libdjvulibre15
libpth20
libtbb2
exim4-config
libhttpcore-java
libgnomekbd2
librecode0
libgnomekbd4
xserver-common
libgnomekbd7
gir1.2-goa-1.0
liblog4j1.2-java
EOF

echo "Create repository $RM_CFG"
RepositoryMirror.py -c $RM_CFG -create

echo "Dumping out info"
RepositoryMirror.py -c $RM_CFG -info

echo "Printing out download summary"
RepositoryMirror.py -c $RM_CFG

echo "Downloading packages"
RepositoryMirror.py -c $RM_CFG -fetch
