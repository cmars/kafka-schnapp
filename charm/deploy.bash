#!/bin/bash

HERE=$(cd $(dirname $0); pwd)
if [ -z "$CHANNEL" ]; then
	CHANNEL=edge
fi
if [ -z "$CHARM_NAME" ]; then
	CHARM_NAME=kafka
fi
if [ -z "$CS_USER" ]; then
	CS_USER=$CHARM_NAME-distillers
fi

set -eu

tmphome=$(mktemp -d)
trap "rm -rf $tmphome" EXIT

export HOME=$tmphome
mkdir -p $HOME/.local/share/juju
echo "$STORE_USSO_TOKEN" | base64 -d > $HOME/.local/share/juju/store-usso-token
chmod 600 $HOME/.local/share/juju/store-usso-token

charm login -B

CHARM_PUSH=$(charm push $HERE/builds/${CHARM_NAME} --resource ${CHARM_NAME}=$HERE/../${CHARM_NAME}_*.snap cs:~${CS_USER}/${CHARM_NAME})
CHARM_REV=$(echo $CHARM_PUSH | awk '/url:/ {print $2}')
RESOURCE_REV=$(charm list-resources --format json $CHARM_REV | jq -r '.[]|"\(.Name)-\(.Revision)"')

echo "Pushed charm $CHARM_REV with resource $RESOURCE_REV"

charm release $CHARM_REV --resource $RESOURCE_REV --channel $CHANNEL
charm grant cs:~${CS_USER}/${CHARM_NAME} --channel $CHANNEL --acl write yellow
charm grant cs:~${CS_USER}/${CHARM_NAME} --channel $CHANNEL --acl read everyone

echo "Released to $CHANNEL channel"

