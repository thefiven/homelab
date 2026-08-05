# homelab

A single-operator, self-hosted execution platform, agnostic to the services it
runs. This glossary fixes the terms whose everyday synonyms are misleading here.

## Language

### The platform and what it runs

**Platform**:
The execution substrate this repository designs and operates. It is the product;
what runs on it is interchangeable.

**Workload**:
Anything the platform runs on behalf of a consumer, as opposed to the platform's
own machinery. A workload's internals are out of scope for a platform decision.
_Avoid_: Application, service — when the distinction from the platform matters

### The resource budget

The three terms below are routinely conflated and mean different things. See
[ADR-0002](./docs/adr/0002-resource-budget-and-feasibility-verdict.md).

**Envelope**:
The share of a finite machine resource allocated to one consumer by the resource
budget. It is a decision, not an observation.
_Avoid_: Quota, budget, allowance

**Reservation**:
What a consumer declares it needs, checked at admission. This is what makes the
sum of all envelopes true.
_Avoid_: Request — except when naming an orchestrator's own field

**Cap**:
The point beyond which a consumer is throttled or killed. This is what makes one
consumer's overrun someone else's non-problem.
_Avoid_: Limit, ceiling, max

**Standard slot**:
The unit envelope an ordinary workload receives without arguing for one — an
application plus its database. Platform capacity is stated in slots.

**Reserved floor**:
The part of the machine consumed before any workload sees it: host, filesystem
cache, control plane, GitOps engine, observability.

**Slack**:
Machine resource deliberately left unallocated. It is not spare capacity and is
not available to a workload.
_Avoid_: Headroom, spare, margin
