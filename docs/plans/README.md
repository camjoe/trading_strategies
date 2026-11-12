# Plans

Type: index
Status: Active
Created: 2026-10-11
Last Reviewed: 2026-10-11
Purpose: List the forward-looking plans that are not yet built, with the status and trigger of each.
Related: [Docs Index](../README.md), [Docs Authoring Standard](../conventions/docs-authoring.md)

## Overview

A plan describes work that is not built. A plan that ships becomes a reference note or an ADR.
Then delete the plan. Use `Type: plan` in the header.

## Usage

Add a plan as a new file in this folder. Add a row to the table below and an entry in
[`docs/maps/docs-map.md`](../maps/docs-map.md). When a plan ships, move the lasting facts to a
reference note or an ADR and delete the plan.

## Plans

| Plan | Status | Trigger |
|---|---|---|
| [Adaptive Learning (P10)](adaptive-learning.md) | Active (deferred) | A rankable advisor scorecard group with decisions in more than one regime |
| [Project-Agnostic Tooling](project-agnostic-tooling.md) | Draft | A second project needs the screenshot or check-runner tool |
| [Web UI](ui.md) | Active | Open items on the features/command-catalog branch; the first is the CI pipeline commit |
