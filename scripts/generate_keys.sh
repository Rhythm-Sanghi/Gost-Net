#!/bin/bash

KEYSTORE_NAME="ghostnet.keystore"
ALIAS_NAME="ghostnet-release-key"
VALIDITY_DAYS=10000
KEY_SIZE=2048

if [ -f "$KEYSTORE_NAME" ]; then
    read -p "Keystore already exists. Overwrite? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Keystore generation cancelled."
        exit 1
    fi
    rm "$KEYSTORE_NAME"
fi

read -sp "Enter keystore password: " KEYSTORE_PASSWORD
echo
read -sp "Confirm keystore password: " KEYSTORE_PASSWORD_CONFIRM
echo

if [ "$KEYSTORE_PASSWORD" != "$KEYSTORE_PASSWORD_CONFIRM" ]; then
    echo "Passwords do not match. Exiting."
    exit 1
fi

read -sp "Enter key password (or press Enter for same as keystore): " KEY_PASSWORD
echo

if [ -z "$KEY_PASSWORD" ]; then
    KEY_PASSWORD="$KEYSTORE_PASSWORD"
fi

keytool -genkey -v \
    -keystore "$KEYSTORE_NAME" \
    -keyalg RSA \
    -keysize "$KEY_SIZE" \
    -validity "$VALIDITY_DAYS" \
    -alias "$ALIAS_NAME" \
    -storepass "$KEYSTORE_PASSWORD" \
    -keypass "$KEY_PASSWORD" \
    -dname "CN=Ghost Net Release, OU=Security, O=Ghost Net, C=US"

if [ $? -eq 0 ]; then
    echo ""
    echo "✓ Keystore generated successfully!"
    echo "  Keystore: $KEYSTORE_NAME"
    echo "  Alias: $ALIAS_NAME"
    echo "  Validity: $VALIDITY_DAYS days"
    echo "  Key Size: $KEY_SIZE-bit RSA"
    echo ""
    echo "Export these variables before building:"
    echo "  export P4A_RELEASE_KEYSTORE='$(pwd)/$KEYSTORE_NAME'"
    echo "  export P4A_RELEASE_KEYSTORE_PASSWD='$KEYSTORE_PASSWORD'"
    echo "  export P4A_RELEASE_KEYALIAS='$ALIAS_NAME'"
    echo "  export P4A_RELEASE_KEYALIAS_PASSWD='$KEY_PASSWORD'"
else
    echo "✗ Keystore generation failed!"
    exit 1
fi
