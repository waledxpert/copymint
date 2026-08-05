-- Local development only. Production signer credentials are provisioned out of band.
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'copymint_signer') THEN
    CREATE ROLE copymint_signer LOGIN PASSWORD 'signer_local_only';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE copymint TO copymint_signer;
