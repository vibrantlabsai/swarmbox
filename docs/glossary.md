---
title: Glossary
description: The words the swarmbox docs and SDK use, and what each one means.
group: Reference
weight: 1
---

# Glossary

The words these docs and the SDK use, and what each one means. Use them as defined here; each lists the words to avoid for it.

## World

The group of Sandboxes created for a single trial. They share a private network and reach each other by name, and are placed, started, and destroyed together: the set is fixed when the World is created, and one Sandbox failing fails the World. The platform's unit of placement, lifecycle, and accounting.

_Avoid_: environment, pod, cluster, group

## Sandbox

One isolated container: an agent's workspace, a mock service, or a verifier. Every Sandbox belongs to exactly one World.

_Avoid_: box, machine, container (when the platform unit is meant)

## Trial

One run of one task by one agent, scored by the task's verifier. The word is Harbor's. Each trial gets a World of its own.

_Avoid_: run, job (a Harbor job is a set of trials)

## Rollout

One episode of an agent acting on a task, as RL training counts them. Run through Harbor, a rollout is a trial.

_Avoid_: episode, run

## Environment

The definition of an RL task family: its images, tools, verifier, and task instances. Owned by the Environment author, not by the platform.

_Avoid_: env image, task image

## Environment author

A person who packages an Environment so its trials run as Worlds. Distinct from a User, who runs trials of an existing Environment; one person can be both.

_Avoid_: task author, benchmark author

## User

A person or service that holds an API token and creates Worlds. Each person is their own User; a service User is never shared with a person.

_Avoid_: tenant, account, principal, tester

## Built image

An image the platform built from a User's build context (a Dockerfile and its files). Every node runs it; only that User's uploads can change it.

_Avoid_: pushed image, task image

## Egress

What a single Sandbox may reach outside its World. Declared per Sandbox, enforced by the platform; Sandboxes of the same World can always reach each other.

_Avoid_: network rules, firewall

## Execution signal

What the platform reports back from a Sandbox: exit codes, stdout/stderr, files. The platform never computes rewards; turning execution signals into rewards belongs to the Environment's verifier.

_Avoid_: reward, score (when talking about platform output)

## Platform

The swarmbox software that runs Worlds: the API servers, the node agents and the builder.

_Avoid_: cluster, backend

## Test bed

A place the platform runs for development or benchmarking, such as the hosted test bed the [quickstart](quickstart.md) uses.

_Avoid_: environment (that is an RL task family)
