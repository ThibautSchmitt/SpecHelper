# HTTPS with Caddy

The optional [HTTPS Compose configuration](../compose.https.yaml) places Caddy in
front of the frontend. It removes the direct frontend port 3000, publishes TCP
80/443 and UDP 443 for HTTP/3, and redirects HTTP to HTTPS. API, database and runtime
ports remain private. Caddy shares only the frontend ingress network.

## Enable HTTPS

Set a hostname in `.env`, without `https://`, a port or a path:

```dotenv
SPECHELPER_DOMAIN=localhost
```

Then activate HTTPS with the existing application images:

```sh
docker compose -f compose.yaml -f compose.https.yaml config --quiet
docker compose -f compose.yaml -f compose.https.yaml up -d
```

Open <https://localhost>. The override derives allowed hosts and the trusted HTTPS
origin from `SPECHELPER_DOMAIN` and enables trusted TLS forwarding and secure cookies.
Wait for active analyses before recreating backend/worker to change their environment.
Caddy replaces client-supplied forwarding headers, preserves the upload limit and
streams responses without adding automatic retries of publication requests.

On macOS, Docker Desktop must be allowed to publish ports 80 and 443. If startup
reports `Ports are not available` or `not allowed as current user`, enable
**Settings → Advanced → Allow privileged port mapping** and apply the change.
Creating the container through the VM's raw Docker socket can bypass this check
without making the ports reachable on macOS; use Docker Desktop's normal socket.

Keep both Compose files for subsequent commands. On macOS/Linux, this `.env` entry
also makes ordinary `docker compose` commands retain HTTPS mode:

```dotenv
COMPOSE_FILE=compose.yaml:compose.https.yaml
```

## Local certificates

Caddy creates a local certificate authority for `localhost`. Docker cannot install
it in the host browser's trust store. Export only the public root certificate:

```sh
mkdir -p .local/caddy
docker compose -f compose.yaml -f compose.https.yaml cp caddy:/data/caddy/pki/authorities/local/root.crt .local/caddy/root.crt
openssl x509 -in .local/caddy/root.crt -noout -subject -fingerprint -sha256
```

Review that certificate before trusting it. On macOS, the following adds trust to
the current user's login keychain, restricted to SSL for `localhost`:

```sh
security add-trusted-cert -r trustRoot -p ssl -s localhost -k "$HOME/Library/Keychains/login.keychain-db" .local/caddy/root.crt
```

Other operating systems/browsers require importing the public root into their trust
store. Clients without that trust report a certificate error. Command-line tools
with an independent CA store can verify the same certificate explicitly:

```sh
curl --cacert .local/caddy/root.crt https://localhost/api/health
```

Never export or share the CA's private key. The test runner creates a separate CA
and never installs it on the host.

## Public hostnames

Use the actual hostname, for example `SPECHELPER_DOMAIN=spechelper.example.com`.
Point its DNS records to the server and allow incoming TCP 80/443; UDP 443 is optional.
Set `BIND_ADDRESS=0.0.0.0` only when remote exposure is intended and configure the
existing shared access password described in [SECURITY](../SECURITY.md). Remote
access without valid authentication continues to fail closed.

Caddy obtains and renews a public certificate when the domain and ACME validation
are reachable. No DNS provider token is required for this HTTP/TLS challenge setup.
The supplied configuration accepts one exact hostname, without wildcard DNS setup.

## Persistent certificates and reloads

The `caddy-data` volume retains certificates, CA private keys and ACME account data.
Preserve it across restarts/upgrades and protect its backups. `caddy-config` retains
the saved Caddy configuration. The administrator API is container-local and is not
published. The supplied Caddyfile does not enable access logging.

The [Caddyfile](../deploy/caddy/Caddyfile) is mounted as a directory, allowing atomic
file replacement and reloads without restarting the application:

```sh
docker compose -f compose.yaml -f compose.https.yaml exec caddy caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile
docker compose -f compose.yaml -f compose.https.yaml exec caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile
```

A hostname change also changes application host/origin settings. Update `.env` and
recreate the relevant services with both Compose files; reloading Caddy alone does
not update backend settings. To return to local HTTP, remove the `COMPOSE_FILE` entry
and explicitly use only `compose.yaml`; stop the unused Caddy service as well.

## Validation

The disposable HTTPS test exercises the production Caddy configuration with fictional
data and no host ports or production volumes:

```sh
bash scripts/security/dast.sh https
```

This verifies the proxy and application boundary, not public DNS reachability or an
external certificate authority's availability. See [Security testing](security-testing.md).
