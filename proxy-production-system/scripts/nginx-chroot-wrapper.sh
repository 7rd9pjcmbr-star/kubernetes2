#!/usr/bin/env bash

# Copyright 2022 The Kubernetes Authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

set -euo pipefail

CHROOT_DIR="${CHROOT_DIR:-/chroot}"
RESOLV_CONF_SRC="${RESOLV_CONF_SRC:-/etc/resolv.conf}"
RUN_AS_UID="${RUN_AS_UID:-101}"
NGINX_BIN="${NGINX_BIN:-nginx}"
RESOLV_CONF_DST="${CHROOT_DIR}/etc/resolv.conf"

fail() {
  echo "error: $*" >&2
  exit 1
}

command -v unshare >/dev/null 2>&1 || fail "missing required command: unshare"
command -v "${NGINX_BIN}" >/dev/null 2>&1 || fail "missing required command: ${NGINX_BIN}"

[[ -r "${RESOLV_CONF_SRC}" ]] || fail "cannot read resolv.conf source: ${RESOLV_CONF_SRC}"
[[ -d "${CHROOT_DIR}" ]] || fail "chroot directory does not exist: ${CHROOT_DIR}"

mkdir -p "${CHROOT_DIR}/etc"

# Write via temporary file then move for an atomic update.
tmp_file="$(mktemp "${CHROOT_DIR}/etc/resolv.conf.tmp.XXXXXX")"
trap 'rm -f "${tmp_file}"' EXIT
cat "${RESOLV_CONF_SRC}" > "${tmp_file}"
chmod 0644 "${tmp_file}"
mv "${tmp_file}" "${RESOLV_CONF_DST}"
trap - EXIT

exec unshare -S "${RUN_AS_UID}" -R "${CHROOT_DIR}" "${NGINX_BIN}" "$@"
