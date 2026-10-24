> Historical snapshot, archived on 2026-10-24. Statements and test counts below describe
> their original review, not the current product or deployment. Start with the
> [active documentation](../../overview.md) and [current limitations](../../known-limitations.md).

# GitHub Copilot adapter evaluation

Review date: 2026-10-23. Status: **experimental evaluation; unavailable for production
analysis**. SpecHelper does not install a Copilot runtime, accept Copilot credentials
or silently substitute Copilot for Codex/Claude. No Copilot subscription or paid
inference was used for this review.

## Supported platform surfaces and integration gaps

| Area | Official platform evidence | SpecHelper decision and remaining validation |
| --- | --- | --- |
| Authentication | The SDK documents signed-in GitHub users, OAuth applications and environment-based credentials, as well as separate organization/BYOK modes. | A future adapter must use an explicitly authorized identity and encrypted credential lifecycle. A source-repository token is not automatically a Copilot entitlement or publication credential. Device login, refresh, revocation and account identity have not been validated here. |
| Models | Copilot exposes model selection and the SDK documents `models.list`. | Discover actual returned models and their underlying families; provider name alone cannot establish model diversity. No hard-coded Copilot model list is supplied. |
| Quotas and billing | SDK metadata includes `account.getQuota`, model pricing and session usage events. Some quota RPC surfaces are experimental. | Pin compatible CLI/SDK versions and validate real account grouping, freshness, resets and error states. Do not translate a Copilot budget into Codex/Claude five-hour or weekly windows without actual evidence. Billing can depend on plan and usage; do not assume every plan uses legacy premium-request multipliers. |
| Sessions | SDK persistence and resume retain conversation and tool state; resume can change model and tools. | Use separate role contexts, scoped session storage and application locking. Verify cold resume, history preservation, cancellation and output-schema translation before enabling execution. |
| Tools and hooks | SDK permission callbacks and pre-tool hooks can reject tools. Repository hooks can execute commands when their workspace is admitted. Server guidance distinguishes empty mode from ambient CLI mode. | Declarative SpecHelper definitions must never become executable hook configuration. Disable ambient hooks/plugins/MCP and retain the external UID/capability/seccomp/filesystem boundary. SDK callbacks alone do not replace the sandbox. |
| Network and provider relay | Copilot can use different transports and provider endpoints; CLI tool sandboxing is narrower than sandboxing the CLI process. | Capture and review exact endpoints, authentication headers, redirects, streaming and resume behavior. Implement an identity-scoped relay and repeat arbitrary-egress/secret/socket/source-write probes. This target-environment validation is outstanding. |

## Activation gate

Production activation requires reproducible evidence for all rows above, the v1.9
Linux containment probes, independent role histories, bounded outputs/resources,
safe account-scoped quota observations, no reusable credentials visible to analysis,
and no source/database writes. A failure must stop the adapter or provide an
explicit administrator choice; it must never switch to a more permissive tool.

Current evidence is documentation review only, not an integration test or a claim
that the installed SpecHelper runtime supports Copilot. Authentication, billing
terms and provider documentation can change; review them again before implementation.

## Primary sources

- [Copilot SDK authentication](https://docs.github.com/en/copilot/how-tos/copilot-sdk/auth/authenticate)
- [Usage and billing metrics](https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/usage-and-billing)
- [Session persistence and resume](https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/session-persistence)
- [Hooks and permission controls](https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/hooks)
- [Server deployment modes and isolation responsibilities](https://docs.github.com/en/copilot/how-tos/copilot-sdk/setup/multi-tenancy)
- [CLI sandboxing scope](https://docs.github.com/en/copilot/how-tos/copilot-cli/use-copilot-cli/overview)
- [Legacy versus usage-based billing](https://docs.github.com/en/copilot/reference/copilot-billing/request-based-billing-legacy/what-changed-with-billing)

## Existing adapter catalog limits

Codex model discovery uses the installed app-server's bounded `model/list` protocol,
in a private temporary home without project hooks/configuration. It does not create
a thread or submit a turn. A returned model is **supported by the adapter catalog**,
not necessarily entitled for that account. Only an actual successful analysis records
availability for that identity and model. See the official
[app-server catalog warning](https://developers.openai.com/siwc/token-sharing-open-source/codex-app-server)
and [model-list protocol](https://github.com/openai/codex/blob/main/codex-rs/app-server/README.md).

The Claude CLI integration currently has no validated non-inference discovery
surface. Its catalog is administered explicitly and remains unknown until actual
analysis provides evidence. A successful authentication or quota refresh is never
reported as a model-availability test.
