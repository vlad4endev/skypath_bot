#!/bin/bash
# Безопасная загрузка .env в bash (значения могут содержать пробелы).
load_env_file() {
    local file="${1:-.env}"
    [ -f "$file" ] || return 1

    set -a
    while IFS= read -r line || [ -n "$line" ]; do
        line="${line//$'\r'/}"
        case "$line" in
            ''|\#*) continue ;;
        esac

        if [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            key="${BASH_REMATCH[1]}"
            val="${BASH_REMATCH[2]}"
            # Снять обрамляющие кавычки
            if [[ "$val" =~ ^\"(.*)\"$ ]]; then
                val="${BASH_REMATCH[1]}"
            elif [[ "$val" =~ ^\'(.*)\'$ ]]; then
                val="${BASH_REMATCH[1]}"
            fi
            export "${key}=${val}"
        fi
    done < "$file"
    set +a
}

# source scripts/load_env.sh .env  → загрузить файл
if [[ "${BASH_SOURCE[0]}" != "${0}" ]] && [[ -n "${1:-}" ]]; then
    load_env_file "$1"
fi
