#!/usr/bin/env bash
# ============================================================================
# Plan or deploy the MLOps feature store + ML pipeline to one environment.
#
#   scripts/deploy_env.sh <DEV|PROD> plan     # read-only (PR checks)
#   scripts/deploy_env.sh <DEV|PROD> deploy   # bootstrap → feature apply → dcm deploy
#
# Auth: CI uses SNOWFLAKE_* env vars (temporary connection, OIDC token from
# snowflakedb/snowflake-actions). Locally:
#   SNOWFLAKE_CONNECTION=<name> SNOWFLAKE_ROLE=MLOPS_DEV_DEPLOYER \
#   SNOWFLAKE_ACCOUNT=<ORG-ACCOUNT> scripts/deploy_env.sh DEV deploy
# Required env: SNOWFLAKE_ACCOUNT (canonical ORG-ACCOUNT form, fills manifests).
# ============================================================================
set -euo pipefail

TARGET="${1:?usage: deploy_env.sh <DEV|PROD> <plan|deploy>}"
MODE="${2:?usage: deploy_env.sh <DEV|PROD> <plan|deploy>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

case "$TARGET" in
  DEV)  DB=DEV_MLOPS_DB ;;
  PROD) DB=PRD_MLOPS_DB ;;
  *) echo "unknown target: $TARGET" >&2; exit 2 ;;
esac
DCM_PROJECT="$DB.MODELS.MLOPS_PIPELINE"

# Connection: CI uses a temporary connection from SNOWFLAKE_* env vars (`-x`,
# OIDC). Locally, set SNOWFLAKE_CONNECTION=<name> to reuse a named connection
# and its cached login; SNOWFLAKE_ROLE (if set) selects the deployer role.
if [[ -n "${SNOWFLAKE_CONNECTION:-}" ]]; then
  CONN=(-c "$SNOWFLAKE_CONNECTION" ${SNOWFLAKE_ROLE:+--role "$SNOWFLAKE_ROLE"})
else
  CONN=(-x)
fi

# Work on a copy so the manifests' <YOUR_ORG>-<YOUR_ACCOUNT> placeholder can be
# filled in without touching the checkout.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp -R "$ROOT/resources/feature_store" "$ROOT/resources/pipeline" "$WORK/"
sed -i.bak "s/<YOUR_ORG>-<YOUR_ACCOUNT>/${SNOWFLAKE_ACCOUNT:?SNOWFLAKE_ACCOUNT not set}/" \
  "$WORK/feature_store/manifest.yml" "$WORK/pipeline/manifest.yml"

echo "::group::[$TARGET] connection"
snow connection test "${CONN[@]}"
echo "::endgroup::"

if [[ "$MODE" == "deploy" ]]; then
  echo "::group::[$TARGET] bootstrap ($DB)"
  snow sql "${CONN[@]}" -f "$ROOT/scripts/bootstrap_env.sql" -D "db=$DB"
  # Ensure the feature-store schema/metadata exist. Run in a scratch copy:
  # init also exports deployed objects into sources/, which must not mix with
  # the authored definitions.
  cp -R "$WORK/feature_store" "$WORK/fs_init"
  (cd "$WORK/fs_init" && snow feature init --yaml --target "$TARGET" "${CONN[@]}")
  echo "::endgroup::"
fi

echo "::group::[$TARGET] feature store plan"
(cd "$WORK/feature_store" && snow feature plan --target "$TARGET" "${CONN[@]}")
echo "::endgroup::"

if [[ "$MODE" == "deploy" ]]; then
  echo "::group::[$TARGET] feature store apply"
  # No --destructive: RECREATE_FV / DROP_* must go through a new FV version
  # or a deliberate manual apply.
  (cd "$WORK/feature_store" && snow feature apply --target "$TARGET" "${CONN[@]}")
  echo "::endgroup::"
fi

echo "::group::[$TARGET] DCM plan"
(cd "$WORK/pipeline" && snow dcm plan "$DCM_PROJECT" --target "$TARGET" "${CONN[@]}")
echo "::endgroup::"

if [[ "$MODE" == "deploy" ]]; then
  echo "::group::[$TARGET] DCM deploy"
  ALIAS="gh-${GITHUB_RUN_ID:-local}-${GITHUB_SHA:0:7}"
  (cd "$WORK/pipeline" && snow dcm deploy "$DCM_PROJECT" --target "$TARGET" --alias "$ALIAS" "${CONN[@]}")
  echo "::endgroup::"
fi
