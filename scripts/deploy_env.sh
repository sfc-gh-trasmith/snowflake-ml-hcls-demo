#!/usr/bin/env bash
# ============================================================================
# Plan or deploy the SnowHealth feature store + ML pipeline to one environment.
#
#   scripts/deploy_env.sh <DEV|PROD> plan     # read-only (PR checks)
#   scripts/deploy_env.sh <DEV|PROD> deploy   # bootstrap → feature apply → dcm deploy
#
# Auth comes from SNOWFLAKE_* env vars (temporary connection, `-x`), e.g. the
# OIDC token set up by snowflakedb/snowflake-actions in GitHub Actions.
# Required env: SNOWFLAKE_ACCOUNT (canonical ORG-ACCOUNT form).
# ============================================================================
set -euo pipefail

TARGET="${1:?usage: deploy_env.sh <DEV|PROD> <plan|deploy>}"
MODE="${2:?usage: deploy_env.sh <DEV|PROD> <plan|deploy>}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

case "$TARGET" in
  DEV)  DB=DEV_SNOWHEALTH_ML_DB ;;
  PROD) DB=PRD_SNOWHEALTH_ML_DB ;;
  *) echo "unknown target: $TARGET" >&2; exit 2 ;;
esac
DCM_PROJECT="$DB.SNOWHEALTH_MODELS.SNOWHEALTH_PIPELINE"

# Work on a copy so the manifests' <YOUR_ORG>-<YOUR_ACCOUNT> placeholder can be
# filled in without touching the checkout.
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
cp -R "$ROOT/resources/feature_store" "$ROOT/resources/pipeline" "$WORK/"
sed -i.bak "s/<YOUR_ORG>-<YOUR_ACCOUNT>/${SNOWFLAKE_ACCOUNT:?SNOWFLAKE_ACCOUNT not set}/" \
  "$WORK/feature_store/manifest.yml" "$WORK/pipeline/manifest.yml"

echo "::group::[$TARGET] connection"
snow connection test -x
echo "::endgroup::"

if [[ "$MODE" == "deploy" ]]; then
  echo "::group::[$TARGET] bootstrap ($DB)"
  snow sql -x -f "$ROOT/scripts/bootstrap_env.sql" -D "db=$DB"
  # Ensure the feature-store schema/metadata exist. Run in a scratch copy:
  # init also exports deployed objects into sources/, which must not mix with
  # the authored definitions.
  cp -R "$WORK/feature_store" "$WORK/fs_init"
  (cd "$WORK/fs_init" && snow feature init --yaml --target "$TARGET" -x)
  echo "::endgroup::"
fi

echo "::group::[$TARGET] feature store plan"
(cd "$WORK/feature_store" && snow feature plan --target "$TARGET" -x)
echo "::endgroup::"

if [[ "$MODE" == "deploy" ]]; then
  echo "::group::[$TARGET] feature store apply"
  # No --destructive: RECREATE_FV / DROP_* must go through a new FV version
  # or a deliberate manual apply.
  (cd "$WORK/feature_store" && snow feature apply --target "$TARGET" -x)
  echo "::endgroup::"
fi

echo "::group::[$TARGET] DCM plan"
(cd "$WORK/pipeline" && snow dcm plan "$DCM_PROJECT" --target "$TARGET" -x)
echo "::endgroup::"

if [[ "$MODE" == "deploy" ]]; then
  echo "::group::[$TARGET] DCM deploy"
  ALIAS="gh-${GITHUB_RUN_ID:-local}-${GITHUB_SHA:0:7}"
  (cd "$WORK/pipeline" && snow dcm deploy "$DCM_PROJECT" --target "$TARGET" --alias "$ALIAS" -x)
  echo "::endgroup::"
fi
