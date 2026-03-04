#!/bin/sh
set -e

# Tuning is applied via docker-compose -c flags for the primary.
# This script can be used for any additional one-time DB setup.
echo "TrustDocs PostgreSQL ready."
