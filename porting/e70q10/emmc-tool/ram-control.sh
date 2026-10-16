#!/bin/sh
BB=/bin/busybox
fail() { echo "STOP: $*" >&2;return 1; }
read_control() {
 CONF_FORMAT=;CONF_MANIFEST=;CONF_TARGETS=;CONF_AUTO=;CONF_REBOOT=;CONF_OPERATION=;CONF_BACKUP=;CONF_JOB=;CONF_DATA=;CONF_PART=;CONF_CACHE=;SEEN=' '
 [ -f "$1/update.conf" ] || { fail 'update.conf absent';return 1; }
 while IFS= read -r LINE || [ -n "$LINE" ]; do
  case "$LINE" in *=*) KEY=${LINE%%=*};VALUE=${LINE#*=};; *) fail 'invalid control line';return 1;; esac
  case "$SEEN" in *" $KEY "*) fail 'duplicate control';return 1;; esac;SEEN="$SEEN$KEY "
  case "$KEY" in
   format) case "$VALUE" in 4|5) CONF_FORMAT=$VALUE;; *) fail 'requires format=4 or 5';return 1;; esac;;
   manifest) [ "$VALUE" = '@MANIFEST@' ] || { fail 'RAM and package differ';return 1; };CONF_MANIFEST=$VALUE;;
   targets) case "$VALUE" in boot|system|vendor|system,vendor|system,boot|vendor,boot|system,vendor,boot|none) CONF_TARGETS=$VALUE;; *) fail 'bad targets';return 1;; esac;;
   autostart) case "$VALUE" in 0|1) CONF_AUTO=$VALUE;; *) return 1;; esac;;
   reboot) case "$VALUE" in 0|1) CONF_REBOOT=$VALUE;; *) return 1;; esac;;
   operation) case "$VALUE" in install|update|install-test|backup) CONF_OPERATION=$VALUE;; *) return 1;; esac;;
   backup) case "$VALUE" in required|none) CONF_BACKUP=$VALUE;; *) return 1;; esac;;
   job) [ "${#VALUE}" = 32 ] || return 1;case "$VALUE" in *[!0-9a-f]*) return 1;; esac;CONF_JOB=$VALUE;;
   userdata) case "$VALUE" in create|preserve) CONF_DATA=$VALUE;; *) return 1;; esac;;
   partitioning) case "$VALUE" in create|preserve) CONF_PART=$VALUE;; *) return 1;; esac;;
   cache) case "$VALUE" in create|preserve) CONF_CACHE=$VALUE;; *) return 1;; esac;;
   *) fail 'unknown control key' ;return 1;;
  esac
 done < "$1/update.conf"
 for KEY in format manifest targets autostart reboot operation backup job userdata partitioning cache; do case "$SEEN" in *" $KEY "*) ;; *) fail 'missing control key';return 1;; esac;done
 # Legacy format4 retains its mandatory/disabled backup policy.
 if [ "$CONF_FORMAT" = 4 ]; then
  case "$CONF_OPERATION:$CONF_BACKUP" in install:required|install-test:required|backup:required|update:none) ;; *) fail 'legacy backup policy mismatch';return 1;; esac
 fi
 case "$CONF_OPERATION" in
 install) [ "$CONF_TARGETS" = system,vendor,boot ] && [ "$CONF_DATA" = create ] && [ "$CONF_PART" = create ] && [ "$CONF_CACHE" = create ] || { fail 'invalid destructive install policy';return 1; };;
 install-test) [ "$CONF_BACKUP" = required ] && [ "$CONF_TARGETS" = system,vendor,boot ] && [ "$CONF_DATA" = preserve ] && [ "$CONF_PART" = preserve ] && [ "$CONF_CACHE" = create ] || { fail 'test must preserve data and partitioning';return 1; };;
 backup) [ "$CONF_BACKUP" = required ] && [ "$CONF_TARGETS" = none ] && [ "$CONF_DATA" = preserve ] && [ "$CONF_PART" = preserve ] && [ "$CONF_CACHE" = preserve ] && [ "$CONF_REBOOT" = 0 ] || { fail 'backup must preserve all internal data and remain in RAM';return 1; };;
 update) [ "$CONF_TARGETS" != none ] && [ "$CONF_DATA" = preserve ] && [ "$CONF_PART" = preserve ] && [ "$CONF_CACHE" = preserve ] || return 1;;
 esac
}
