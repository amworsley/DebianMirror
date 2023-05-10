#! /bin/bash

# Hardcoded defaults Put overrides configuration into /etc/RepositoryMirror/RM.sh
# Directory of RepositoryMirror 
BPATH=$(dirname $0)
SCRIPT=$BPATH/RepositoryMirror.py
if [ -x "$SCRIPT" ]; then
    RM="$BPATH"
elif [ -x "/usr/local/bin/RepositoryMirror.py" ]; then
    RM="/usr/local/bin"
    SCRIPT=$RM/RepositoryMirror.py
else
    RM="/usr/bin"
    SCRIPT=$RM/RepositoryMirror.py
fi

# Default configuration files
# Old
# jessie.cfg jessie-updates.cfg jessie-updates-security.cfg
#        stretch-updates-security.cfg stretch.cfg stretch-updates.cfg
DCONFIGS=( lts-stretch.cfg lts-stretch-updates-security.cfg
        buster.cfg buster-updates.cfg buster-updates-security.cfg )
OPTS=""

# Put customisation configuration into DEF_FILE
DEFS="RM-defs.sh"
DEF_FILE=/etc/RepositoryMirror/$DEFS
if [ -e "$BPATH/$DEFS" ]; then
    DEF_FILE="$BPATH/$DEFS"
    echo "Reading $DEF_FILE"
    . $DEF_FILE
elif [ -e $DEF_FILE ]; then
    echo "Reading $DEF_FILE"
    . $DEF_FILE
else
    echo "Using defaults"
fi

usage()
{
   echo "$(basename $0) [options] <config-file> ..."
   echo " Update mirrors using RepositoryMirror.py script"
   echo ""
   echo "-C <config> : Use <config> configuration script"
   echo "-M <distribution> : Create a configuration files for given distribution"
   echo "   e.g. buster => buster.cfg (stable point) buster-updates (updates)"
   echo "    buster-updates-security.cfg (buster security updates)"
   echo "-K : Clone the existing mirror using file links - to prune the old mirror"
   echo "-h : Print this usage information"
   echo "-n : Dry-run print commands instead of executing them"
   echo "-x : Enabling tracing of shell script"
   echo "-v : Run with verbose mode"
   echo "-d : Run with debug mode"
   echo "-c : Run with create mode"
   echo "-f : enable fetching of packages"
   echo "-q : only check sizes (not mdsums) - faster"
   echo "-Q : quiet mode - less noisy info"
}

mk_config () {
    local D="$1"
    local F="$D.cfg"
    local R="http://ftp.au.debian.org/debian/"

    echo
    case $D in
    *-updates-security)
	R="http://security.debian.org/"
	echo "Security Updates for ${D%-updates-security}"
    ;;
    *-updates)
	echo "Updates for ${D%-updates}"
    ;;
    *)
	echo "$D Release"
    ;;
    esac

    echo "Configuration file $F"
cat <<EOF
[setup]
repository: $R
distribution: $D
components: main contrib non-free icons Components
architectures: armhf amd64 i386 arm64 all
lmirror: deb-mirror
EOF
}


while getopts 'nxhvdcfqQC:M:K' argv
do
    case $argv in
    M)
       DIST="$OPTARG"
       mk_config "$DIST"
       mk_config "$DIST-updates"
       mk_config "$DIST-updates-security"
       DONE="1"
    ;;
    C)
       DEF_FILE="$OPTARG"
       if [ -r $DEF_FILE ]; then
            echo "Using $DEF_FILE configuration"
            . $DEF_FILE
       else
            echo "Unable to read configuration file $DEF_FILE"
            exit 1
       fi
    ;;
    K)
       KLONE="1"
       OPTS="-create -uselinks $OPTS"
       echo
       echo "    Doing a local *clone*"
       echo
    ;;
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
    Q)
        echo "Enable Quiet mode (no missing messages ...)"
        OPTS="$OPTS -Q"
    ;;
    esac
done

shift $(($OPTIND-1))

if [ -n "$DONE" ]; then
    exit 0
fi

if [ $# -le 0 ]; then
    echo "Using default configurations"
    CONFIGS=( "${DCONFIGS[@]}" )
else
    CONFIGS=( "$@" )
fi

echo "Running configuration files in $RM"
cd $RM

for cfg in ${CONFIGS[@]}; do
    if [ -n "$KLONE" ]; then
	if [ ! -r "$cfg" ]; then
	    echo "Skipping $cfg - file missing"
	    continue
	fi
	lmirror=$(awk '/^lmirror:/ { print $2 }' $cfg)
	if [ -z "$lmirror" ]; then
	    echo "Skipping $cfg - local mirror missing"
	    continue
	fi
	ocfg="$cfg"
	cfg="mirror-$ocfg"
	nlmirror="$lmirror-clone"
	echo "Cloning config $ocfg to $cfg with local mirror in "
	if [ -z "$DR" ]; then
    sed '
     /^repository:/s#: .*#: file:///'"$RM/$lmirror"'#
     /^lmirror:/s/: .*/: '"$nlmirror"'/' $ocfg > $cfg
	else
    $DR sed '
     /^repository:/s#: .*#: file:///'"$RM/$lmirror"'#
     /^lmirror:/s/: .*/: '"$nlmirror"'/' $ocfg \> $cfg
	fi
    fi
    echo "Configuration $cfg:"
    echo  "*** $SCRIPT -c $cfg $OPTS ***"
    $DR cd $RM
    $DR $SCRIPT -c $cfg $OPTS
    echo
done
exit 0
