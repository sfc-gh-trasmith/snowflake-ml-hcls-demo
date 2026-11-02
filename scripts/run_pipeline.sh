#!/usr/bin/env bash
# ============================================================================
# Run the SnowHealth task DAG once in one environment and validate the outputs.
#
#   scripts/run_pipeline.sh <DEV|PROD>
#
# Enables the DAG, triggers the root task, waits for the finalizer, fails if
# any task failed, checks the deploy log, then re-suspends the root so the
# weekly cron only fires where it is intentionally left enabled.
# ============================================================================
set -euo pipefail

TARGET="${1:?usage: run_pipeline.sh <DEV|PROD>}"
case "$TARGET" in
  DEV)  DB=DEV_SNOWHEALTH_ML_DB ;;
  PROD) DB=PRD_SNOWHEALTH_ML_DB ;;
  *) echo "unknown target: $TARGET" >&2; exit 2 ;;
esac
S="$DB.SNOWHEALTH_MODELS"
ROOT_TASK="$S.SNOWHEALTH_PIPELINE_ROOT"
TIMEOUT_MIN="${PIPELINE_TIMEOUT_MIN:-40}"

q() { snow sql -x --format json -q "$1"; }

START="$(q "SELECT TO_CHAR(CURRENT_TIMESTAMP(), 'YYYY-MM-DD HH24:MI:SS.FF3 TZHTZM') AS T" | jq -r '.[0].T')"
q "SELECT SYSTEM\$TASK_DEPENDENTS_ENABLE('$ROOT_TASK')" >/dev/null
q "EXECUTE TASK $ROOT_TASK" >/dev/null
echo "[$TARGET] triggered $ROOT_TASK at $START"

suspend_root() { q "ALTER TASK $ROOT_TASK SUSPEND" >/dev/null || true; }
trap suspend_root EXIT

HISTORY_SQL="SELECT NAME, STATE, ERROR_MESSAGE
  FROM TABLE($DB.INFORMATION_SCHEMA.TASK_HISTORY(
         SCHEDULED_TIME_RANGE_START => '$START'::TIMESTAMP_LTZ, RESULT_LIMIT => 100))
  WHERE NAME LIKE 'SNOWHEALTH%' AND STATE <> 'SCHEDULED'
  ORDER BY SCHEDULED_TIME"

deadline=$(( $(date +%s) + TIMEOUT_MIN * 60 ))
while :; do
  sleep 30
  hist="$(q "$HISTORY_SQL")"
  echo "[$TARGET] $(echo "$hist" | jq -r 'map("\(.NAME|sub("SNOWHEALTH_(TASK_)?";"")):\(.STATE)") | join(" | ")')"
  if echo "$hist" | jq -e 'any(.NAME == "SNOWHEALTH_TASK_NOTIFY_COMPLETION" and (.STATE == "SUCCEEDED" or .STATE == "FAILED"))' >/dev/null; then
    break
  fi
  if (( $(date +%s) > deadline )); then
    echo "::error::[$TARGET] pipeline did not finish within ${TIMEOUT_MIN} minutes"; exit 1
  fi
done

failed="$(echo "$hist" | jq -r '.[] | select(.STATE == "FAILED") | "\(.NAME): \(.ERROR_MESSAGE)"')"
if [[ -n "$failed" ]]; then
  echo "::error::[$TARGET] task(s) failed"; echo "$failed"; exit 1
fi

# Validate: this run promoted a model version that passed the quality gate
LOG="$(q "SELECT VERSION, ROUND(RMSE, 3) AS RMSE, STATUS
  FROM $S.SNOWHEALTH_PIPELINE_DEPLOY_LOG
  WHERE STATUS = 'DEPLOYED' AND DEPLOYED_AT >= CONVERT_TIMEZONE('UTC', '$START'::TIMESTAMP_TZ)::TIMESTAMP_NTZ
  ORDER BY DEPLOYED_AT DESC LIMIT 1")"
if [[ "$(echo "$LOG" | jq 'length')" == "0" ]]; then
  echo "::error::[$TARGET] no DEPLOYED row in SNOWHEALTH_PIPELINE_DEPLOY_LOG for this run"; exit 1
fi
FV_ROWS="$(q "SELECT COUNT(*) AS N FROM $DB.SNOWHEALTH_PIPELINE_FS.\"SNOWHEALTH_PIPELINE_FV\$V1\"" | jq -r '.[0].N')"

SUMMARY="### $TARGET pipeline run ✅
| Check | Result |
|---|---|
| Tasks | all succeeded |
| Feature view rows | $FV_ROWS |
| Promoted model | $(echo "$LOG" | jq -r '.[0].VERSION') (RMSE $(echo "$LOG" | jq -r '.[0].RMSE')) |"
echo "$SUMMARY"
[[ -n "${GITHUB_STEP_SUMMARY:-}" ]] && echo "$SUMMARY" >> "$GITHUB_STEP_SUMMARY"
