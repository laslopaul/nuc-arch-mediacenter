#!/usr/bin/env bash
# docker_cleanup.sh — Remove unused Docker images
# Usage: ./docker_cleanup.sh [OPTIONS]
#   -a    Remove ALL unused images (not just dangling)
#   -f    Force removal without confirmation prompt
#   -d    Dry run: show what would be removed, but don't delete
#   -h    Show this help message

set -euo pipefail

# ── Defaults ──────────────────────────────────────────────────────────────────
REMOVE_ALL=false
FORCE=false
DRY_RUN=false

# ── Colors ────────────────────────────────────────────────────────────────────
RED='\033[0;31m'
YELLOW='\033[1;33m'
GREEN='\033[0;32m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ── Parse flags ───────────────────────────────────────────────────────────────
while getopts "afedh" opt; do
  case $opt in
    a) REMOVE_ALL=true ;;
    f) FORCE=true ;;
    d) DRY_RUN=true ;;
    h)
      sed -n '2,8p' "$0" | sed 's/^# //'
      exit 0
      ;;
    *) echo "Unknown option: -$OPTARG"; exit 1 ;;
  esac
done

# ── Helpers ───────────────────────────────────────────────────────────────────
require_docker() {
  if ! command -v docker &>/dev/null; then
    echo -e "${RED}Error:${RESET} docker is not installed or not in PATH." >&2
    exit 1
  fi
  if ! docker info &>/dev/null; then
    echo -e "${RED}Error:${RESET} Docker daemon is not running (or permission denied)." >&2
    exit 1
  fi
}

human_size() {
  # Sum reclaimable bytes reported by docker image prune --dry-run
  docker image prune ${1:---filter dangling=true} --dry-run --format '{{.SpaceReclaimed}}' 2>/dev/null || echo "unknown"
}

# ── Main ──────────────────────────────────────────────────────────────────────
require_docker

PRUNE_FLAGS=""
LABEL="dangling (untagged)"
if $REMOVE_ALL; then
  PRUNE_FLAGS="--all"
  LABEL="all unused"
fi

echo -e "${BOLD}${CYAN}Docker Image Cleanup${RESET}"
echo "────────────────────────────────────"

# Collect images that would be removed
if $REMOVE_ALL; then
  # Get the full image IDs of every image currently referenced by a container
  # (running *or* stopped) so we never list or remove them.
  USED_IDS=$(docker ps -aq | xargs -r docker inspect --format '{{.Image}}' 2>/dev/null | sort -u)

  # List all images, then drop any whose full ID appears in USED_IDS
  IMAGES=""
  while IFS= read -r line; do
    full_id=$(echo "$line" | awk '{print $1}')
    if ! echo "$USED_IDS" | grep -qF "$full_id"; then
      short_id=$(echo "$full_id" | cut -c8-19)   # strip "sha256:" prefix, take 12 chars
      rest=$(echo "$line" | awk '{print $2, $3}')
      IMAGES+="${short_id} ${rest}"$'\n'
    fi
  done < <(docker images --no-trunc --format "{{.ID}} {{.Repository}}:{{.Tag}} {{.Size}}" 2>/dev/null)
  IMAGES="${IMAGES%$'\n'}"   # trim trailing newline
else
  IMAGES=$(docker images --filter "dangling=true" --format "{{.ID}} {{.Repository}}:{{.Tag}} {{.Size}}" 2>/dev/null)
fi

if [[ -z "$IMAGES" ]]; then
  echo -e "${GREEN}✔ No ${LABEL} images found. Nothing to remove.${RESET}"
  exit 0
fi

echo -e "The following ${BOLD}${LABEL}${RESET} images will be removed:\n"
printf "  %-15s %-45s %s\n" "IMAGE ID" "REPOSITORY:TAG" "SIZE"
printf "  %-15s %-45s %s\n" "───────────────" "─────────────────────────────────────────────" "──────"
while IFS= read -r line; do
  id=$(echo "$line" | awk '{print $1}' | cut -c1-12)
  tag=$(echo "$line" | awk '{print $2}')
  size=$(echo "$line" | awk '{print $3}')
  printf "  ${YELLOW}%-15s${RESET} %-45s %s\n" "$id" "$tag" "$size"
done <<< "$IMAGES"
echo ""

IMAGE_COUNT=$(echo "$IMAGES" | wc -l | tr -d ' ')
echo -e "  ${BOLD}Total:${RESET} ${IMAGE_COUNT} image(s)"
echo ""

# Dry run — stop here
if $DRY_RUN; then
  echo -e "${CYAN}[Dry run]${RESET} No images were removed."
  exit 0
fi

# Confirmation prompt (skip with -f)
if ! $FORCE; then
  read -r -p "$(echo -e "${BOLD}Proceed with removal?${RESET} [y/N] ")" answer
  case "$answer" in
    [yY][eE][sS]|[yY]) ;;
    *)
      echo "Aborted."
      exit 0
      ;;
  esac
fi

# Perform removal
echo ""
echo -e "${BOLD}Removing images...${RESET}"
if docker image prune $PRUNE_FLAGS --force; then
  echo ""
  echo -e "${GREEN}✔ Done.${RESET} Unused Docker images removed successfully."
else
  echo -e "${RED}✘ Something went wrong during pruning.${RESET}" >&2
  exit 1
fi
