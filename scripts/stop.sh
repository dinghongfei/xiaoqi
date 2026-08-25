#!/usr/bin/env bash
set -euo pipefail
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# shellcheck source=process.sh
source "$PROJECT_ROOT/scripts/process.sh"
stop_project_services
