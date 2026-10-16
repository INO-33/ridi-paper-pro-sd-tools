# This is RAM-owned code. SD update.conf is parsed as data, never sourced.
read_config() {
    CONF_TARGETS=;CONF_AUTO=;CONF_REBOOT=;cf_seen='|';cf_count=0
    [ -f "$1/update.conf" ] || { echo 'STOP: update.conf missing' >&2;return 1; }
    while IFS= read -r cf_line || [ -n "$cf_line" ]; do
        cf_key=${cf_line%%=*};cf_value=${cf_line#*=}
        case "$cf_seen" in *"|$cf_key|"*) echo 'STOP: duplicate config key' >&2;return 1;; esac
        cf_seen="$cf_seen$cf_key|";cf_count=$((cf_count+1))
        case "$cf_key:$cf_value" in
            format:1|manifest:@MANIFEST@) ;;
            targets:system|targets:vendor|targets:boot|targets:system,vendor|targets:system,boot|targets:vendor,boot|targets:system,vendor,boot) CONF_TARGETS=$cf_value;;
            autostart:0|autostart:1) CONF_AUTO=$cf_value;;
            reboot:0|reboot:1) CONF_REBOOT=$cf_value;;
            *) echo 'STOP: invalid update.conf' >&2;return 1;;
        esac
    done < "$1/update.conf"
    [ "$cf_count" = 5 ] && [ -n "$CONF_TARGETS" ] && [ -n "$CONF_AUTO" ] && [ -n "$CONF_REBOOT" ] || { echo 'STOP: incomplete update.conf' >&2;return 1; }
}
is_selected() { case ",$CONF_TARGETS," in *",$1,"*) return 0;; *) return 1;; esac; }
