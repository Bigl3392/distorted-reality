#!/bin/sh
# Text template: install only after a separate operator decision.
set -eu
docker_path='<<DOCKER_ABSOLUTE_PATH>>'
case "$docker_path" in *'<<'*|'') echo 'Unresolved Docker path' >&2; exit 2;; esac
case "${SSH_ORIGINAL_COMMAND-}" in
 'docker system dial-stdio') exec "$docker_path" system dial-stdio ;;
 *) echo 'Command refused' >&2; exit 126 ;;
esac
