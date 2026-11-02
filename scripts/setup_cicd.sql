-- ============================================================================
-- MLOps with DCM — one-time account setup (run as ACCOUNTADMIN)
--
-- Single account, two environments:
--   DEV  → DEV_MLOPS_DB  (deployed by SVC_MLOPS_GH_DEV  as MLOPS_DEV_DEPLOYER)
--   PROD → PRD_MLOPS_DB  (deployed by SVC_MLOPS_GH_PROD as MLOPS_PROD_DEPLOYER)
--
-- Each GitHub environment (dev / prod) authenticates via OIDC to its own
-- service user, which can only use its own deployer role. Compute
-- (COMPUTE_WH, MLOPS_COMPUTE_POOL) is shared; data and objects are not.
--
--   snow sql -f scripts/setup_cicd.sql -c <admin_connection>
--
-- Idempotent. Re-running is safe. To adopt in another repo, change the two
-- OIDC SUBJECT values (gh api repos/<owner>/<repo>/actions/oidc/customization/sub).
-- ============================================================================
USE ROLE ACCOUNTADMIN;

-- ── Deployer roles ──────────────────────────────────────────────────────────
CREATE ROLE IF NOT EXISTS MLOPS_DEV_DEPLOYER
    COMMENT = 'Deploys the MLOps feature store + DCM pipeline to DEV_MLOPS_DB';
CREATE ROLE IF NOT EXISTS MLOPS_PROD_DEPLOYER
    COMMENT = 'Deploys the MLOps feature store + DCM pipeline to PRD_MLOPS_DB';
-- Roll up so admins (and the interactive notebooks) keep access
GRANT ROLE MLOPS_DEV_DEPLOYER TO ROLE SYSADMIN;
GRANT ROLE MLOPS_PROD_DEPLOYER TO ROLE SYSADMIN;

-- ── Shared compute ──────────────────────────────────────────────────────────
CREATE COMPUTE POOL IF NOT EXISTS MLOPS_COMPUTE_POOL
    MIN_NODES = 1
    MAX_NODES = 5
    INSTANCE_FAMILY = CPU_X64_S
    AUTO_RESUME = TRUE
    AUTO_SUSPEND_SECS = 600
    COMMENT = 'MLOps template — ML Jobs (code bundles), tuning, model serving';

GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE MLOPS_DEV_DEPLOYER;
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE MLOPS_PROD_DEPLOYER;
GRANT USAGE, MONITOR ON COMPUTE POOL MLOPS_COMPUTE_POOL TO ROLE MLOPS_DEV_DEPLOYER;
GRANT USAGE, MONITOR ON COMPUTE POOL MLOPS_COMPUTE_POOL TO ROLE MLOPS_PROD_DEPLOYER;
GRANT EXECUTE TASK ON ACCOUNT TO ROLE MLOPS_DEV_DEPLOYER;
GRANT EXECUTE TASK ON ACCOUNT TO ROLE MLOPS_PROD_DEPLOYER;

-- ── Environment databases (each owned end-to-end by its deployer) ───────────
CREATE DATABASE IF NOT EXISTS DEV_MLOPS_DB COMMENT = 'MLOps with DCM — DEV';
CREATE SCHEMA IF NOT EXISTS DEV_MLOPS_DB.RAW COMMENT = 'Source data (DEV) — loaded by ingestion, not CI';
CREATE SCHEMA IF NOT EXISTS DEV_MLOPS_DB.MODELS COMMENT = 'DCM pipeline objects + model registry (DEV)';
GRANT OWNERSHIP ON DATABASE DEV_MLOPS_DB TO ROLE MLOPS_DEV_DEPLOYER COPY CURRENT GRANTS;
GRANT OWNERSHIP ON ALL SCHEMAS IN DATABASE DEV_MLOPS_DB TO ROLE MLOPS_DEV_DEPLOYER COPY CURRENT GRANTS;

CREATE DATABASE IF NOT EXISTS PRD_MLOPS_DB COMMENT = 'MLOps with DCM — PROD';
CREATE SCHEMA IF NOT EXISTS PRD_MLOPS_DB.RAW COMMENT = 'Source data (PROD) — loaded by ingestion, not CI';
CREATE SCHEMA IF NOT EXISTS PRD_MLOPS_DB.MODELS COMMENT = 'DCM pipeline objects + model registry (PROD)';
GRANT OWNERSHIP ON DATABASE PRD_MLOPS_DB TO ROLE MLOPS_PROD_DEPLOYER COPY CURRENT GRANTS;
GRANT OWNERSHIP ON ALL SCHEMAS IN DATABASE PRD_MLOPS_DB TO ROLE MLOPS_PROD_DEPLOYER COPY CURRENT GRANTS;

-- ── Service users (OIDC, one per GitHub environment) ────────────────────────
CREATE USER IF NOT EXISTS SVC_MLOPS_GH_DEV
    TYPE = SERVICE
    DEFAULT_ROLE = MLOPS_DEV_DEPLOYER
    DEFAULT_WAREHOUSE = COMPUTE_WH
    COMMENT = 'GitHub Actions (environment: dev) — MLOps with DCM template';
CREATE USER IF NOT EXISTS SVC_MLOPS_GH_PROD
    TYPE = SERVICE
    DEFAULT_ROLE = MLOPS_PROD_DEPLOYER
    DEFAULT_WAREHOUSE = COMPUTE_WH
    COMMENT = 'GitHub Actions (environment: prod) — MLOps with DCM template';

-- Subject format (GitHub immutable subjects):
--   repo:<owner>@<owner_id>/<repo>@<repo_id>:environment:<env>
ALTER USER SVC_MLOPS_GH_DEV SET WORKLOAD_IDENTITY = (
    TYPE = OIDC
    ISSUER = 'https://token.actions.githubusercontent.com'
    SUBJECT = 'repo:sfc-gh-trasmith@256389544/snowflake-ml-hcls-demo@1407872279:environment:dev');
ALTER USER SVC_MLOPS_GH_PROD SET WORKLOAD_IDENTITY = (
    TYPE = OIDC
    ISSUER = 'https://token.actions.githubusercontent.com'
    SUBJECT = 'repo:sfc-gh-trasmith@256389544/snowflake-ml-hcls-demo@1407872279:environment:prod');

GRANT ROLE MLOPS_DEV_DEPLOYER TO USER SVC_MLOPS_GH_DEV;
GRANT ROLE MLOPS_PROD_DEPLOYER TO USER SVC_MLOPS_GH_PROD;

-- If the account has an account-level network policy, scope an allow-list
-- policy (managed rule SNOWFLAKE.NETWORK_SECURITY.GITHUBACTIONS_GLOBAL) to the
-- service users only. Harmless when no account policy exists.
CREATE NETWORK POLICY IF NOT EXISTS GITHUB_ACTIONS_POLICY
    ALLOWED_NETWORK_RULE_LIST = ('SNOWFLAKE.NETWORK_SECURITY.GITHUBACTIONS_GLOBAL')
    COMMENT = 'Allow GitHub Actions runners via managed network rule';
ALTER USER SVC_MLOPS_GH_DEV SET NETWORK_POLICY = GITHUB_ACTIONS_POLICY;
ALTER USER SVC_MLOPS_GH_PROD SET NETWORK_POLICY = GITHUB_ACTIONS_POLICY;
