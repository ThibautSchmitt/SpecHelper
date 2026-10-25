CREATE TABLE qualification_settings (
  name text PRIMARY KEY,
  value text NOT NULL,
  effective_from date NOT NULL
);
CREATE TABLE qualification_contracts (
  id integer PRIMARY KEY,
  status text NOT NULL,
  open_claims integer NOT NULL,
  imported boolean NOT NULL,
  updated_on date NOT NULL
);
CREATE TABLE qualification_invoices (
  id integer PRIMARY KEY,
  status text NOT NULL,
  dispute_open boolean NOT NULL,
  paid_on date NOT NULL
);
