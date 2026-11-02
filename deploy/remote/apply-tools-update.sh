#!/bin/sh
set -eu

fail() {
    printf 'ERROR: %s\n' "$*" >&2
    exit 1
}
[ "$#" -eq 3 ] || fail 'usage: apply-tools-update.sh ABSOLUTE_UPDATE_TAR EXPECTED_SHA256 ABSOLUTE_TRIAL_ROOT'
ARCHIVE=$1
EXPECTED=$2
TARGET=$3
case "$ARCHIVE" in /*) ;; *) fail 'update tar must be an absolute path' ;; esac
case "$TARGET" in /*) ;; *) fail 'trial root must be an absolute path' ;; esac
printf '%s' "$EXPECTED" | awk 'length == 64 && $0 ~ /^[0-9a-f]+$/ {ok=1} END {exit !ok}' || fail 'expected update SHA256 must be 64 lowercase hex characters'
[ -f "$ARCHIVE" ] && [ ! -L "$ARCHIVE" ] || fail 'update tar must be an ordinary non-symlink file'
ACTUAL=$(sha256sum "$ARCHIVE")
ACTUAL=${ACTUAL%% *}
[ "$ACTUAL" = "$EXPECTED" ] || fail 'update tar SHA256 differs from the independently supplied reviewed value'
FILES='
deploy/remote/.gitattributes
deploy/remote/.gitignore
deploy/remote/SOURCE_SHA256SUMS
deploy/remote/apply-tools-update.sh
deploy/remote/compose.yml
deploy/remote/docker.sh
deploy/remote/image-rootfs-layers.txt
deploy/remote/preflight.sh
deploy/remote/release.env
deploy/remote/trial.sh
deploy/remote/update-from-240b9a8.sha256
deploy/remote/verify_backup.py
deploy/remote/verify_image_archive.py
docs/REMOTE_TRIAL.md
'
STAGING=$(mktemp -d "${TMPDIR:-/tmp}/crm-c010400-update.XXXXXX")
trap 'rm -rf "$STAGING"' EXIT
tar -tf "$ARCHIVE" | awk '!/\/$/' | LC_ALL=C sort > "$STAGING/actual-files"
printf '%s\n' $FILES | LC_ALL=C sort > "$STAGING/expected-files"
cmp -s "$STAGING/actual-files" "$STAGING/expected-files" || fail 'update tar does not contain exactly the reviewed tool/document whitelist'
tar -tvf "$ARCHIVE" | awk '$1 !~ /^-/ && $1 !~ /^d/ {bad=1} END {exit bad}' || fail 'update tar contains a link or special member'
while IFS= read -r ITEM; do
    case "$ITEM" in
        /*|../*|*/../*|*/..) fail 'update tar contains an unsafe path' ;;
    esac
done <<EOF
$(tar -tf "$ARCHIVE")
EOF
tar -xf "$ARCHIVE" -C "$STAGING"
for FILE in $FILES; do
    [ -f "$STAGING/$FILE" ] && [ ! -L "$STAGING/$FILE" ] || fail "update member is missing or not an ordinary file: $FILE"
done
[ -d "$TARGET" ] && [ ! -L "$TARGET" ] || fail 'trial root must be an existing non-symlink directory'
[ -d "$TARGET/deploy/remote" ] && [ ! -L "$TARGET/deploy/remote" ] || fail 'existing tool directory must be real and non-symlink'
[ -d "$TARGET/deploy/remote/.runtime" ] && [ ! -L "$TARGET/deploy/remote/.runtime" ] || fail 'existing dev-owned runtime must be present and non-symlink'
[ -f "$TARGET/deploy/remote/.runtime/.env" ] && [ ! -L "$TARGET/deploy/remote/.runtime/.env" ] || fail 'existing .env must be preserved as an ordinary non-symlink file'
[ -f "$TARGET/deploy/remote/.runtime/image.env" ] && [ ! -L "$TARGET/deploy/remote/.runtime/image.env" ] || fail 'existing image lock must be preserved as an ordinary non-symlink file'
while read -r HASH FILE; do
    ACTUAL_OLD=$(sed 's/\r$//' "$TARGET/$FILE" | sha256sum)
    ACTUAL_OLD=${ACTUAL_OLD%% *}
    [ "$ACTUAL_OLD" = "$HASH" ] || fail "existing tools differ from reviewed 240b9a8 content after LF normalization: $FILE"
done <<EOF
$(cat "$STAGING/deploy/remote/update-from-240b9a8.sha256")
EOF
BACKUP="$TARGET/deploy/remote.pre-c010400-update"
[ ! -e "$BACKUP" ] && [ ! -L "$BACKUP" ] || fail 'previous tool backup already exists; preserve it and investigate'
mkdir -p "$BACKUP/deploy/remote" "$BACKUP/docs"
while read -r HASH FILE; do
    cp -a "$TARGET/$FILE" "$BACKUP/$FILE" || fail 'old tool backup failed; no new tool was installed'
done <<EOF
$(cat "$STAGING/deploy/remote/update-from-240b9a8.sha256")
EOF
for FILE in $FILES; do
    [ ! -L "$TARGET/$FILE" ] || fail "target update path is a symlink: $FILE"
done
for FILE in $FILES; do
    cp "$STAGING/$FILE" "$TARGET/$FILE" || fail 'tool update failed or was interrupted; stop and do not migrate or check'
done
EXPECTED_GROUP=$(cd "$STAGING" && for FILE in $FILES; do sha256sum "$FILE"; done)
ACTUAL_GROUP=$(cd "$TARGET" && for FILE in $FILES; do sha256sum "$FILE"; done)
[ "$ACTUAL_GROUP" = "$EXPECTED_GROUP" ] || fail 'updated tool group differs from staging; stop and do not migrate or check'
printf 'PASS: exact tool group updated; old tools retained at %s; runtime, apps and Docker resources untouched\n' "$BACKUP"
