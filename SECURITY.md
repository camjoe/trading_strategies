# Security Policy

## Project status

This project is educational and research software under active development. It is not represented as
production-ready investment infrastructure. No released version currently receives a formal security
support commitment.

Security reports involving broker connections, order submission, credentials, authorization, or the
possibility of unintended trades are especially important.

## Reporting a vulnerability

Do not include credentials, account identifiers, private trading data, or exploitable details in a
public issue.

Use GitHub private vulnerability reporting when it is available for this repository. If it is not
available, contact the repository owner privately before sharing sensitive details. A sanitized public
issue is appropriate only when it contains no secret, personal, account, or immediately exploitable
information.

Include, when safe:

- The affected component and revision.
- Reproduction steps using paper or simulated trading only.
- Potential impact, especially whether live orders or secret exposure are possible.
- Any suggested mitigation.

Do not test a suspected vulnerability against an account, broker service, or system you do not own or
have explicit permission to use.

## Operational safety

- Use paper or simulated accounts for reproduction.
- Keep real credentials in ignored local environment files or an external secret store.
- Review broker configuration and live-trading gates before enabling any broker integration.
- Treat logs, database exports, screenshots, and issue attachments as potentially sensitive.

This policy is a reporting and coordination guide, not a warranty or security guarantee.
