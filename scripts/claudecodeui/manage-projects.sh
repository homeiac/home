#!/bin/bash
# Manage claudecodeui projects (clone, list, pull)
set -e

NAMESPACE="claudecodeui"
DEPLOYMENT="claudecodeui"

usage() {
    echo "Usage: $0 <command> [args]"
    echo ""
    echo "Commands:"
    echo "  list              - List projects in container"
    echo "  clone <url>       - Clone a repo into projects directory"
    echo "  pull <project>    - Git pull in a project"
    echo "  exec <command>    - Run arbitrary command in container"
    echo ""
    echo "Examples:"
    echo "  $0 list"
    echo "  $0 clone https://github.com/homeiac/home.git"
    echo "  $0 pull home"
    echo "  $0 exec 'ls -la /home/claude/projects'"
}

k_exec() {
    KUBECONFIG=~/kubeconfig kubectl exec -n "$NAMESPACE" "deploy/$DEPLOYMENT" -- bash -c "$1"
}

case "${1:-}" in
    list)
        echo "=== Projects in /home/claude/projects ==="
        k_exec "ls -la /home/claude/projects/"
        ;;
    clone)
        if [[ -z "${2:-}" ]]; then
            echo "ERROR: URL required"
            usage
            exit 1
        fi
        echo "=== Cloning $2 ==="
        k_exec "cd /home/claude/projects && git clone $2"
        echo ""
        echo "Projects now:"
        k_exec "ls -la /home/claude/projects/"
        ;;
    pull)
        if [[ -z "${2:-}" ]]; then
            echo "ERROR: Project name required"
            usage
            exit 1
        fi
        echo "=== Pulling $2 ==="
        k_exec "cd /home/claude/projects/$2 && git pull"
        ;;
    exec)
        if [[ -z "${2:-}" ]]; then
            echo "ERROR: Command required"
            usage
            exit 1
        fi
        k_exec "$2"
        ;;
    *)
        usage
        exit 1
        ;;
esac
