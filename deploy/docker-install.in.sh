#!/bin/sh
# PREPARED TEXT, NOT RUN. Repository/keyring bootstrap requires operator review first.
set -eu
engine='<<G4_DOCKER_VERSION>>'
cli='<<PINNED_DOCKER_CLI_VERSION>>'
containerd='<<PINNED_CONTAINERD_VERSION>>'
buildx='<<PINNED_BUILDX_VERSION>>'
compose='<<PINNED_COMPOSE_VERSION>>'
host_plan='<<G8_PLAN_REGION_OS>>'
for value in "$engine" "$cli" "$containerd" "$buildx" "$compose" "$host_plan"; do
 case "$value" in *'<<'*|UNSET|'') echo 'Unresolved build/host input; refusing' >&2; exit 2;; esac
done
printf 'Candidate: docker-ce=%s, docker-ce-cli=%s, containerd.io=%s\n' "$engine" "$cli" "$containerd"
printf 'Type INSTALL only after the exact host/install is authorized: '
read -r answer
[ "$answer" = INSTALL ] || exit 2
apt-get install --no-install-recommends "docker-ce=$engine" "docker-ce-cli=$cli" "containerd.io=$containerd" "docker-buildx-plugin=$buildx" "docker-compose-plugin=$compose"
docker version
