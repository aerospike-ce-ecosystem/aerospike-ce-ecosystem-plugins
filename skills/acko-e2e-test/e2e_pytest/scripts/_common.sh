# shellcheck shell=bash
# Shared defaults and tiny logging — sourced by every script in this dir.
set -euo pipefail

: "${KIND_CLUSTER:=aerospike-ce-kubernetes-operator-test-e2e}"
: "${CONTAINER_TOOL:=podman}"
: "${KIND_PROVIDER:=podman}"
: "${KIND_EXPERIMENTAL_PROVIDER:=$KIND_PROVIDER}"
: "${NS_OPERATOR:=aerospike-operator}"
: "${NS_AEROSPIKE:=aerospike}"
: "${NS_OTEL:=otel}"
: "${NS_CERT_MANAGER:=cert-manager}"
: "${HELM_RELEASE:=acko}"
: "${IMG:=ghcr.io/aerospike-ce-ecosystem/aerospike-ce-kubernetes-operator:v0.0.1}"
: "${API_IMG:=ghcr.io/aerospike-ce-ecosystem/aerospike-cluster-manager-api:latest}"
: "${COLLECTOR_IMAGE:=docker.io/otel/opentelemetry-collector-contrib:latest}"
: "${CERT_MANAGER_VERSION:=v1.19.3}"
: "${OPERATOR_REPO:=$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../../../aerospike-ce-kubernetes-operator" 2>/dev/null && pwd || echo "")}"
: "${CHART_PATH:=${OPERATOR_REPO}/charts/aerospike-ce-kubernetes-operator}"

export KIND_CLUSTER CONTAINER_TOOL KIND_PROVIDER KIND_EXPERIMENTAL_PROVIDER

log()   { printf '[%s] %s\n' "$(date +%H:%M:%S)" "$*" >&2; }
die()   { printf '[%s ERR] %s\n' "$(date +%H:%M:%S)" "$*" >&2; exit 1; }
