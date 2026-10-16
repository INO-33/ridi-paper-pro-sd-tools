#!/usr/bin/env bash
set -euo pipefail

workspace=/home/juwon/ridi
source_tree="$workspace/android-sources/nxp-o8.0.0_1.0.0-ga"
java_home="$workspace/host-tools/jdk8-local/usr/lib/jvm/java-8-openjdk-amd64"
tool_bin="$workspace/host-tools/android8-bin"

if [[ ! -x "$java_home/bin/javac" ]]; then
    echo "Missing local Java 8 compiler: $java_home/bin/javac" >&2
    exit 1
fi

if [[ ! -x "$tool_bin/python" ]]; then
    echo "Missing Android Python 2 wrapper: $tool_bin/python" >&2
    exit 1
fi

export JAVA_HOME="$java_home"
export PATH="$tool_bin:$JAVA_HOME/bin:$PATH"
export LD_LIBRARY_PATH="$JAVA_HOME/lib/amd64/jli${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
export HOSTCFLAGS=-fcommon
export LC_ALL=C
export USE_CCACHE=0
jack_security="$source_tree/device/ridi/e70q10/tools/jack-java.security"
export ANDROID_JACK_VM_ARGS="${ANDROID_JACK_VM_ARGS:--Dfile.encoding=UTF-8 -XX:+TieredCompilation -Djava.security.properties=$jack_security}"

lunch_target="${E70Q10_LUNCH:-e70q10_minimal-eng}"
product_name="${lunch_target%-*}"
export OUT_DIR="${E70Q10_OUT_DIR:-$workspace/android-out/$product_name}"

cd "$source_tree"
# shellcheck disable=SC1091
set +u
source build/envsetup.sh >/dev/null
lunch "$lunch_target" >/dev/null
set -u

case "${1:-check}" in
    check)
        echo "Android build environment ready"
        echo "  target:  ${TARGET_PRODUCT}-${TARGET_BUILD_VARIANT}"
        echo "  output:  $OUT_DIR"
        echo "  java:    $("$JAVA_HOME/bin/javac" -version 2>&1)"
        echo "  python:  $(python --version 2>&1)"
        echo "  free:    $(df -h "$workspace" | awk 'NR == 2 {print $4}')"
        ;;
    build)
        shift
        jobs="${E70Q10_BUILD_JOBS:-6}"
        min_free_gb="${E70Q10_MIN_FREE_GB:-25}"
        out_parent="$(dirname "$OUT_DIR")"
        if [[ ! -d "$out_parent" ]]; then
            echo "Missing OUT_DIR parent: $out_parent" >&2
            exit 1
        fi
        free_kb="$(df -Pk "$out_parent" | awk 'NR == 2 {print $4}')"
        min_free_kb="$((min_free_gb * 1024 * 1024))"
        if (( free_kb < min_free_kb )); then
            echo "Refusing build: ${free_kb} KiB free, ${min_free_kb} KiB required" >&2
            exit 1
        fi
        if [[ "$#" -eq 0 ]]; then
            set -- droid
        fi
        # HWC/gralloc are on the separate vendor partition; keep the sleep
        # extension producer and the framework consumer in the same build.
        want_system=0
        want_vendor=0
        for build_target in "$@"; do
            [[ "$build_target" != systemimage ]] || want_system=1
            [[ "$build_target" != vendorimage ]] || want_vendor=1
        done
        if (( want_system && !want_vendor )); then
            set -- "$@" vendorimage
            echo "Adding vendorimage: apply system.img and vendor.img together"
        fi
        echo "Building $* with -j$jobs into $OUT_DIR"
        make -j"$jobs" "$@"
        ;;
    *)
        echo "Usage: $0 [check | build [make-target ...]]" >&2
        exit 2
        ;;
esac
