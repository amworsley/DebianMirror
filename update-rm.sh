#! /bin/bash

# Hardcoded defaults Put overrides configuration into /etc/RepositoryMirror/RM.sh
# Directory of RepositoryMirror 
RM=/movies3/deb-mirror
# Path to RepositoryMirror.py script
RMPATH=.
#SCRIPT=$RM/RepositoryMirror.py
SCRIPT=/usr/local/bin/RepositoryMirror.py

# Default configuration files
#DCONFIGS=( jessie.cfg jessie-updates.cfg jessie-updates-security.cfg )
DCONFIGS=( stretch.cfg stretch-updates.cfg stretch-updates-security.cfg
        buster.cfg buster-updates.cfg buster-updates-security.cfg )
OPTS=""

# Put customisation configuration into DEF_FILE
DEF_FILE=/etc/RepositoryMirror/RM-defs.sh
if [ -e $DEF_FILE ]; then
    . $DEF_FILE
fi

usage()
{
   echo "$(basename $0): Update mirrors using RepositoryMirror.py script"
   echo ""
   echo "-h : Print this usage information"
   echo "-n : Dry-run print commands instead of executing them"
   echo "-x : Enabling tracing of shell script"
   echo "-v : Run with verbose mode"
   echo "-d : Run with debug mode"
   echo "-c : Run with create mode"
   echo "-f : enable fetching of packages"
   echo "-q : only check sizes (not mdsums) - faster"
}

while getopts 'nxhvdcfq' argv
do
    case $argv in
    n)
       echo "Dry-Run"
       DR=echo
       OPTS="$OPTS -n"
    ;;
    x)
        echo "Enabling tracing"
        set -x
    ;;
    h)
        usage
        exit 0
    ;;
    v)
        echo "verbose mode"
        OPTS="$OPTS -v"
    ;;
    d)
        echo "debug mode"
        OPTS="$OPTS -d"
    ;;
    c)
        echo "create mode"
        OPTS="$OPTS -create"
    ;;
    f)
        echo "fetching packages"
        OPTS="$OPTS -fetch"
    ;;
    q)
        echo "Only check sizes (quicker)"
        OPTS="$OPTS -only-pkgs-size"
    ;;
    esac
done

shift $(($OPTIND-1))

if [ $# -le 0 ]; then
    echo "Using default configurations"
    CONFIGS=( "${DCONFIGS[@]}" )
else
    CONFIGS=( "$@" )
fi

$DR cd $RM

for cfg in ${CONFIGS[@]}; do
    echo "Updating $cfg:"
    $DR $SCRIPT -c $cfg $OPTS
    if [ -z "$DR" ]; then
        cd $RM
        $SCRIPT -c $cfg $OPTS
    fi
    echo
done
exit 0
