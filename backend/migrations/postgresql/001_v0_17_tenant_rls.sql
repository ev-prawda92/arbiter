-- Arbiter v0.17 PostgreSQL tenant RLS reference migration
-- Run only after all application tables exist and historical rows have explicit tenant ownership.
-- The runtime migration in backend/app/production_data.py performs the same policy setup and fails closed on NULL tenant ownership.

BEGIN;

-- contract_versions
ALTER TABLE IF EXISTS contract_versions ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS contract_versions ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS contract_versions ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_contract_versions_tenant ON contract_versions(tenant_id);
ALTER TABLE IF EXISTS contract_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS contract_versions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_contract_versions ON contract_versions;
CREATE POLICY arbiter_tenant_contract_versions ON contract_versions USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- authority_versions
ALTER TABLE IF EXISTS authority_versions ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS authority_versions ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS authority_versions ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_authority_versions_tenant ON authority_versions(tenant_id);
ALTER TABLE IF EXISTS authority_versions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS authority_versions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_authority_versions ON authority_versions;
CREATE POLICY arbiter_tenant_authority_versions ON authority_versions USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- evidence_records
ALTER TABLE IF EXISTS evidence_records ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS evidence_records ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS evidence_records ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_evidence_records_tenant ON evidence_records(tenant_id);
ALTER TABLE IF EXISTS evidence_records ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS evidence_records FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_evidence_records ON evidence_records;
CREATE POLICY arbiter_tenant_evidence_records ON evidence_records USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- resolution_runs
ALTER TABLE IF EXISTS resolution_runs ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS resolution_runs ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS resolution_runs ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_resolution_runs_tenant ON resolution_runs(tenant_id);
ALTER TABLE IF EXISTS resolution_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS resolution_runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_resolution_runs ON resolution_runs;
CREATE POLICY arbiter_tenant_resolution_runs ON resolution_runs USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- audit_events
ALTER TABLE IF EXISTS audit_events ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS audit_events ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS audit_events ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_audit_events_tenant ON audit_events(tenant_id);
ALTER TABLE IF EXISTS audit_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS audit_events FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_audit_events ON audit_events;
CREATE POLICY arbiter_tenant_audit_events ON audit_events USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- work_item_state
ALTER TABLE IF EXISTS work_item_state ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS work_item_state ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS work_item_state ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_work_item_state_tenant ON work_item_state(tenant_id);
ALTER TABLE IF EXISTS work_item_state ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS work_item_state FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_work_item_state ON work_item_state;
CREATE POLICY arbiter_tenant_work_item_state ON work_item_state USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- analysis_cases
ALTER TABLE IF EXISTS analysis_cases ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS analysis_cases ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS analysis_cases ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_analysis_cases_tenant ON analysis_cases(tenant_id);
ALTER TABLE IF EXISTS analysis_cases ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS analysis_cases FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_analysis_cases ON analysis_cases;
CREATE POLICY arbiter_tenant_analysis_cases ON analysis_cases USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- analysis_case_runs
ALTER TABLE IF EXISTS analysis_case_runs ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS analysis_case_runs ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS analysis_case_runs ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_analysis_case_runs_tenant ON analysis_case_runs(tenant_id);
ALTER TABLE IF EXISTS analysis_case_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS analysis_case_runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_analysis_case_runs ON analysis_case_runs;
CREATE POLICY arbiter_tenant_analysis_case_runs ON analysis_case_runs USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- contract_templates
ALTER TABLE IF EXISTS contract_templates ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS contract_templates ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS contract_templates ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_contract_templates_tenant ON contract_templates(tenant_id);
ALTER TABLE IF EXISTS contract_templates ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS contract_templates FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_contract_templates ON contract_templates;
CREATE POLICY arbiter_tenant_contract_templates ON contract_templates USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- principal_registry
ALTER TABLE IF EXISTS principal_registry ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS principal_registry ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS principal_registry ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_principal_registry_tenant ON principal_registry(tenant_id);
ALTER TABLE IF EXISTS principal_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS principal_registry FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_principal_registry ON principal_registry;
CREATE POLICY arbiter_tenant_principal_registry ON principal_registry USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- approval_requests
ALTER TABLE IF EXISTS approval_requests ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS approval_requests ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS approval_requests ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_approval_requests_tenant ON approval_requests(tenant_id);
ALTER TABLE IF EXISTS approval_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS approval_requests FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_approval_requests ON approval_requests;
CREATE POLICY arbiter_tenant_approval_requests ON approval_requests USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- approval_decisions
ALTER TABLE IF EXISTS approval_decisions ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS approval_decisions ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS approval_decisions ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_approval_decisions_tenant ON approval_decisions(tenant_id);
ALTER TABLE IF EXISTS approval_decisions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS approval_decisions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_approval_decisions ON approval_decisions;
CREATE POLICY arbiter_tenant_approval_decisions ON approval_decisions USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- settlement_packets
ALTER TABLE IF EXISTS settlement_packets ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS settlement_packets ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS settlement_packets ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_settlement_packets_tenant ON settlement_packets(tenant_id);
ALTER TABLE IF EXISTS settlement_packets ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS settlement_packets FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_settlement_packets ON settlement_packets;
CREATE POLICY arbiter_tenant_settlement_packets ON settlement_packets USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- evidence_monitors
ALTER TABLE IF EXISTS evidence_monitors ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS evidence_monitors ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS evidence_monitors ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_evidence_monitors_tenant ON evidence_monitors(tenant_id);
ALTER TABLE IF EXISTS evidence_monitors ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS evidence_monitors FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_evidence_monitors ON evidence_monitors;
CREATE POLICY arbiter_tenant_evidence_monitors ON evidence_monitors USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- evidence_poll_runs
ALTER TABLE IF EXISTS evidence_poll_runs ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS evidence_poll_runs ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS evidence_poll_runs ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_evidence_poll_runs_tenant ON evidence_poll_runs(tenant_id);
ALTER TABLE IF EXISTS evidence_poll_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS evidence_poll_runs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_evidence_poll_runs ON evidence_poll_runs;
CREATE POLICY arbiter_tenant_evidence_poll_runs ON evidence_poll_runs USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- evidence_exceptions
ALTER TABLE IF EXISTS evidence_exceptions ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS evidence_exceptions ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS evidence_exceptions ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_evidence_exceptions_tenant ON evidence_exceptions(tenant_id);
ALTER TABLE IF EXISTS evidence_exceptions ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS evidence_exceptions FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_evidence_exceptions ON evidence_exceptions;
CREATE POLICY arbiter_tenant_evidence_exceptions ON evidence_exceptions USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- resolution_reevaluation_requests
ALTER TABLE IF EXISTS resolution_reevaluation_requests ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS resolution_reevaluation_requests ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS resolution_reevaluation_requests ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_resolution_reevaluation_requests_tenant ON resolution_reevaluation_requests(tenant_id);
ALTER TABLE IF EXISTS resolution_reevaluation_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS resolution_reevaluation_requests FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_resolution_reevaluation_requests ON resolution_reevaluation_requests;
CREATE POLICY arbiter_tenant_resolution_reevaluation_requests ON resolution_reevaluation_requests USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- operation_idempotency
ALTER TABLE IF EXISTS operation_idempotency ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS operation_idempotency ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS operation_idempotency ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_operation_idempotency_tenant ON operation_idempotency(tenant_id);
ALTER TABLE IF EXISTS operation_idempotency ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS operation_idempotency FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_operation_idempotency ON operation_idempotency;
CREATE POLICY arbiter_tenant_operation_idempotency ON operation_idempotency USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- durable_jobs
ALTER TABLE IF EXISTS durable_jobs ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS durable_jobs ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS durable_jobs ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_durable_jobs_tenant ON durable_jobs(tenant_id);
ALTER TABLE IF EXISTS durable_jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS durable_jobs FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_durable_jobs ON durable_jobs;
CREATE POLICY arbiter_tenant_durable_jobs ON durable_jobs USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- webhook_deliveries
ALTER TABLE IF EXISTS webhook_deliveries ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS webhook_deliveries ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS webhook_deliveries ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_webhook_deliveries_tenant ON webhook_deliveries(tenant_id);
ALTER TABLE IF EXISTS webhook_deliveries ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS webhook_deliveries FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_webhook_deliveries ON webhook_deliveries;
CREATE POLICY arbiter_tenant_webhook_deliveries ON webhook_deliveries USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- policy_drafts
ALTER TABLE IF EXISTS policy_drafts ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS policy_drafts ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS policy_drafts ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_policy_drafts_tenant ON policy_drafts(tenant_id);
ALTER TABLE IF EXISTS policy_drafts ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS policy_drafts FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_policy_drafts ON policy_drafts;
CREATE POLICY arbiter_tenant_policy_drafts ON policy_drafts USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

-- model_invocations
ALTER TABLE IF EXISTS model_invocations ADD COLUMN IF NOT EXISTS tenant_id TEXT;
ALTER TABLE IF EXISTS model_invocations ALTER COLUMN tenant_id SET DEFAULT current_setting('arbiter.tenant_id', true);
-- REQUIRED BEFORE NEXT LINE FOR EXISTING DATA: assign every NULL tenant_id from authoritative ownership data.
ALTER TABLE IF EXISTS model_invocations ALTER COLUMN tenant_id SET NOT NULL;
CREATE INDEX IF NOT EXISTS ix_model_invocations_tenant ON model_invocations(tenant_id);
ALTER TABLE IF EXISTS model_invocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE IF EXISTS model_invocations FORCE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS arbiter_tenant_model_invocations ON model_invocations;
CREATE POLICY arbiter_tenant_model_invocations ON model_invocations USING (tenant_id = current_setting('arbiter.tenant_id', true)) WITH CHECK (tenant_id = current_setting('arbiter.tenant_id', true));

COMMIT;
