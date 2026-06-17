# Docs explained

## File Structure

AI often prefers long single documents, rather than well organized folder structure and lots of small files

## Reference vs Architecture

docs/reference
- used for facts

docs/architectuure
- used for reasoning


## Maps

### Domains

Domain map tells agents why things exist, how they connect, and which files matter
Structure maps only tell where things live

Domain Maps
- Not too broad
- Not too naroow
- Good check: Could a ticket be assigned to this domain?
- Python Example:

repository-map.md

domains/
├── authentication.md
├── users.md
├── billing.md
├── notifications.md
├── reporting.md
└── budget-requests.md

## Scripts

Instead of asking AI agents to do something like run a skill to update maps. Run a consistent python script which does that work deterministically
- Could consider this for reference and architecture too

## Architecure

Answers: How does this work?

## ADR (Architecture Decision Recording)

Answers: Why was it designed this way
Examples: Why did we choose sqlite? Why do we use service layers?

## Reference

Answers: What exists
Examples: Endpoints, Schemas, Environement Variables, CLI Commands, Configuarion

## Business Rules

Answers: Finance and Market rules

## Runbooks

Answers: How do I perform an operation