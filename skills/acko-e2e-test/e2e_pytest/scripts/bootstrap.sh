#!/usr/bin/env bash
# bootstrap.sh — install / verify the tools the skill needs on a fresh box.
#
# Detects OS (Ubuntu/Debian via apt, macOS via brew) and installs anything
# missing. Idempotent — already-installed tools are left alone.
#
# Run this once before `uv run pytest` on a fresh Claude Code Ubuntu env.
#
# Usage:
#   bash scripts/bootstrap.sh                  # install everything missing
#   bash scripts/bootstrap.sh --check          # only report status, install nothing
#   bash scripts/bootstrap.sh --no-operator    # skip cloning the operator repo
#
# Required tools: uv, kind, podman, kubectl, helm, go, jq
# Optional: yq (some helpers use Python yaml instead — yq is just for ad-hoc debugging)

set -euo pipefail

CHECK_ONLY=0
CLONE_OPERATOR=1
for a in "$@"; do
    case "$a" in
        --check) CHECK_ONLY=1 ;;
        --no-operator) CLONE_OPERATOR=0 ;;
    esac
done

OS="$(uname -s)"
case "$OS" in
    Linux)
        if ! command -v apt >/dev/null 2>&1; then
            echo "Linux without apt — install tools manually (kind, podman, kubectl, helm, go, uv, jq)"
            exit 1
        fi
        PM=apt
        ;;
    Darwin)
        if ! command -v brew >/dev/null 2>&1; then
            echo "macOS without Homebrew — install brew first (https://brew.sh)"
            exit 1
        fi
        PM=brew
        ;;
    *) echo "unsupported OS: $OS"; exit 1 ;;
esac

OPERATOR_DEFAULT="${OPERATOR_REPO:-$HOME/github/aerospike-ce-kubernetes-operator}"

log()   { printf '[bootstrap] %s\n' "$*" >&2; }
have()  { command -v "$1" >/dev/null 2>&1; }

# ----- helpers -----
install_apt() {
    sudo apt update -y && sudo apt install -y "$@"
}
install_brew() {
    brew install "$@"
}

ensure_uv() {
    if have uv; then log "uv ✓"; return; fi
    [ "$CHECK_ONLY" -eq 1 ] && { log "uv ✗ (need to install)"; return 1; }
    log "installing uv via official installer"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    # uv installs into ~/.local/bin — prepend to PATH for the rest of this script
    export PATH="$HOME/.local/bin:$PATH"
}

ensure_kind() {
    if have kind; then log "kind ✓ ($(kind --version | awk '{print $3}'))"; return; fi
    [ "$CHECK_ONLY" -eq 1 ] && { log "kind ✗"; return 1; }
    log "installing kind"
    if [ "$PM" = brew ]; then
        install_brew kind
    else
        local arch; arch="$(go env GOARCH 2>/dev/null || dpkg --print-architecture)"
        sudo curl -fsSL "https://kind.sigs.k8s.io/dl/latest/kind-linux-${arch}" -o /usr/local/bin/kind
        sudo chmod +x /usr/local/bin/kind
    fi
}

ensure_podman() {
    if have podman; then log "podman ✓"; return; fi
    [ "$CHECK_ONLY" -eq 1 ] && { log "podman ✗"; return 1; }
    log "installing podman"
    if [ "$PM" = brew ]; then
        install_brew podman
        # macOS needs an explicit machine
        podman machine init >/dev/null 2>&1 || true
        podman machine start >/dev/null 2>&1 || true
    else
        install_apt podman
    fi
}

ensure_kubectl() {
    if have kubectl; then log "kubectl ✓"; return; fi
    [ "$CHECK_ONLY" -eq 1 ] && { log "kubectl ✗"; return 1; }
    log "installing kubectl"
    if [ "$PM" = brew ]; then
        install_brew kubectl
    else
        install_apt kubectl || install_apt kubernetes-client
    fi
}

ensure_helm() {
    if have helm; then log "helm ✓"; return; fi
    [ "$CHECK_ONLY" -eq 1 ] && { log "helm ✗"; return 1; }
    log "installing helm"
    if [ "$PM" = brew ]; then
        install_brew helm
    else
        curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | sudo bash
    fi
}

ensure_go() {
    if have go; then log "go ✓ ($(go version | awk '{print $3}'))"; return; fi
    [ "$CHECK_ONLY" -eq 1 ] && { log "go ✗"; return 1; }
    log "installing go"
    if [ "$PM" = brew ]; then
        install_brew go
    else
        install_apt golang-go || install_apt golang
    fi
}

ensure_jq() {
    if have jq; then log "jq ✓"; return; fi
    [ "$CHECK_ONLY" -eq 1 ] && { log "jq ✗"; return 1; }
    log "installing jq"
    [ "$PM" = brew ] && install_brew jq || install_apt jq
}

ensure_operator_repo() {
    if [ "$CLONE_OPERATOR" -ne 1 ]; then return; fi
    if [ -d "$OPERATOR_DEFAULT/.git" ]; then
        log "operator repo ✓ ($OPERATOR_DEFAULT)"
        return
    fi
    [ "$CHECK_ONLY" -eq 1 ] && { log "operator repo ✗ (expected at $OPERATOR_DEFAULT)"; return 1; }
    log "cloning aerospike-ce-kubernetes-operator → $OPERATOR_DEFAULT"
    mkdir -p "$(dirname "$OPERATOR_DEFAULT")"
    git clone --depth 50 \
        https://github.com/aerospike-ce-ecosystem/aerospike-ce-kubernetes-operator.git \
        "$OPERATOR_DEFAULT"
    log "set OPERATOR_REPO=$OPERATOR_DEFAULT in your shell rc to make it sticky"
}

ensure_uv
ensure_kind
ensure_podman
ensure_kubectl
ensure_helm
ensure_go
ensure_jq
ensure_operator_repo

if [ "$CHECK_ONLY" -eq 1 ]; then
    log "check complete"
else
    log "bootstrap complete — next: cd e2e_pytest && uv sync && uv run pytest -m chart -v"
fi
