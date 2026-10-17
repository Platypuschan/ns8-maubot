#!/bin/bash

#
# Copyright (C) 2023 Nethesis S.r.l.
# SPDX-License-Identifier: GPL-3.0-or-later
#

# Terminate on error
set -e

# Prepare variables for later use
images=()
# The image will be pushed to GitHub container registry
repobase="${REPOBASE:-ghcr.io/platypuschan}"
# Keep the published image name aligned with module-info.yml, which derives
# "maubot" from the repository name "ns8-maubot".
reponame="maubot"
repository_source="${GITHUB_SERVER_URL:-https://github.com}/${GITHUB_REPOSITORY:-Platypuschan/ns8-maubot}"
# maubot runs from runtime/: the official maubot release image plus current
# Alpine and Python security fixes (docker/run.sh is not used, see
# imageroot/systemd/user/maubot.service). Its tag is derived from the content
# of runtime/; in CI the "runtime" job of publish-images.yml pushes it before
# this script runs. NS8 passes it to the module as MAUBOT_RUNTIME_IMAGE.
maubot_image="$(.github/scripts/runtime-image)"
if [[ -z "${CI:-}" ]] && ! buildah inspect --type image "${maubot_image}" >/dev/null 2>&1; then
	echo "Building the maubot runtime image ${maubot_image}..."
	buildah bud --layers -t "${maubot_image}" runtime
fi
# Keep in sync with the Node.js version used by .github/workflows/validate.yml
NODE_IMAGE="docker.io/library/node:24.20.0"
nodebuilder="nodebuilder-maubot-${NODE_IMAGE##*:}"
# Create a new empty container image
container=$(buildah from scratch)

# Reuse an existing builder container for the same Node.js version, to speed up builds
if ! buildah containers --format "{{.ContainerName}}" | grep -qx "${nodebuilder}"; then
	echo "Pulling NodeJS runtime..."
	buildah from --name "${nodebuilder}" -v "${PWD}:/usr/src:Z" "${NODE_IMAGE}"
fi

echo "Build static UI files with node..."
buildah run \
	--workingdir=/usr/src/ui \
	"${nodebuilder}" \
	sh -c "corepack enable && yarn install --immutable && yarn build"

# Add imageroot directory to the container image
buildah add "${container}" imageroot /imageroot
buildah add "${container}" ui/dist /ui
# Declare the pinned maubot runtime image, one reserved web port and a rootless container.
# IMAGETAG overrides the published module tag (latest by default).
buildah config --entrypoint=/ \
	--label="org.opencontainers.image.source=${repository_source}" \
	--label="org.opencontainers.image.revision=${GITHUB_SHA:-$(git rev-parse HEAD 2>/dev/null || echo unknown)}" \
	--label="org.nethserver.authorizations=traefik@node:routeadm" \
	--label="org.nethserver.tcp-ports-demand=1" \
	--label="org.nethserver.rootfull=0" \
	--label="org.nethserver.min-core=3.23.0" \
	--label="org.nethserver.images=${maubot_image}" \
	"${container}"
# Commit the image
buildah commit "${container}" "${repobase}/${reponame}"

# Append the image URL to the images array
images+=("${repobase}/${reponame}")

#
# NOTICE:
#
# It is possible to build and publish multiple images.
#
# 1. create another buildah container
# 2. add things to it and commit it
# 3. append the image url to the images array
#

#
# Setup CI when pushing to Github.
# Warning! docker::// protocol expects lowercase letters (,,)
if [[ -n "${CI}" ]]; then
	# Set output value for Github Actions
	printf "images=%s\n" "${images[*],,}" >>"${GITHUB_OUTPUT}"
else
	# Just print info for manual push
	printf "Publish the images with:\n\n"
	for image in "${images[@],,}"; do printf "  buildah push %s docker://%s:%s\n" "${image}" "${image}" "${IMAGETAG:-latest}"; done
	printf "\n"
fi
