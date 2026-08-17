---
status: accepted
date: 2026-08-17
tags: [observability, alerting, secrets]
---

# ntfy for the receiver, Healthchecks.io for the witness, and a heartbeat anchored on `node_exporter`

ADR-0004 accepted four alert categories and ADR-0017 raised that to five, and
not one of them routed anywhere: no receiver was named in any accepted ADR, so
the whole set fired into nothing. ADR-0017 also left an explicit dependency
here, because `node_exporter` publishes the `hwmon` metrics the thermal alert
reads and the filesystem metrics ADR-0004's disk alert reads, and if it dies
both stop working **in silence, while the node stays perfectly reachable**.

This ADR names the destination, names the witness, and closes that dependency.
The archived GitLab iteration's own alerting ADR reached ntfy and
Healthchecks.io too; every argument below was re-judged against the accepted
ADR set as it stands, and one of the mechanisms that makes the answer clean did
not exist when the archive was written.

## The receiver: ntfy.sh, and why it no longer needs an adapter

Alertmanager ships native receivers for eighteen services and ntfy is not among
them. What makes ntfy adapter-free here is recent: **Alertmanager 0.32.0,
released 2026-04-08, added full payload templating for the webhook notifier**.
`webhook_config` now takes a `payload` field, a Go template whose output must be
valid JSON, and ntfy publishes from JSON on `POST https://ntfy.sh/` with
`topic`, `title`, `message`, `priority` and `tags`. The two meet exactly, with
`http_config`'s arbitrary `http_headers` as a second path to the same result via
ntfy's `X-Title` and `X-Priority` headers.

Before 0.32.0 the honest comparison would have gone the other way. A raw webhook
to ntfy renders Alertmanager's fixed JSON schema as the notification body, which
is why third-party adapters such as `ntfy-alertmanager` exist at all. This ADR
needs none of them, so it adds **no process** to ADR-0004's 256 MiB
vmalert-plus-Alertmanager line and no home-made code to maintain, which is the
exact cost ADR-0017 refused when it declined the textfile collector.

Against the natively supported alternatives, ntfy wins on what it does not ask
for. Email needs SMTP and an application password, and an alert in an inbox is
read when someone thinks to look. Telegram needs a bot token and a chat ID.
Discord needs a webhook URL and an account. Pushover is natively supported and
templatable but costs money once per platform, and #29 exists to avoid paying.
ntfy asks for nothing: no sign-up, no token, no account.

**The topic is the credential**, not an identifier. ntfy's own documentation is
explicit: "Because there is no sign-up, the topic is essentially a password, so
pick something that's not easily guessable." It is therefore a secret under
ADR-0009 and is never committed in clear.

## The witness: Healthchecks.io, on its free tier

A dead-man switch is accepted. Monitoring hosted on the machine it watches
cannot alert on its own death because it dies with it, and the mechanism that
fixes that is a heartbeat whose **absence** is the alarm. ADR-0004's
node-unreachable alert is not a substitute: it lives inside the thing that
fails. Without a witness, "nothing is notifying" stays indistinguishable from
"everything is healthy", which is the failure mode the whole alert set is
supposed to remove.

**Healthchecks.io, free tier: 20 checks, 100 log entries per check.** Outbound
only, so it needs no open port and sits inside ADR-0011's design rather than
against it, and it adds no machine to maintain, which is what disqualified a
self-hosted VPS witness in the archive and keeps it disqualified under #29.

**Its own notification leaves by its native ntfy integration**, which is
available on a free account. Two third parties, but **one channel and one
application on the phone**: the witness and the alerts land on the same topic.

**Self-hosting either service would be worthless here.** A self-hosted ntfy and
a self-hosted Healthchecks both die with the machine they watch, precisely when
the alert matters. The third-party dependency is not a shortcut taken for
cheapness, it is the property being bought.

## The heartbeat is anchored on `node_exporter`, not on `vector(1)`

ADR-0017 rejected an `absent()` rule on the exporter for two reasons: it watches
the monitoring from inside the monitoring, which is the flaw a dead-man switch
exists to fix, and it would cost a sixth alert on a list just raised to five.

The answer here costs neither. The always-firing Watchdog alert that carries the
heartbeat is **not** `vector(1)`: its expression is anchored on a metric that
only exists while `node_exporter` is actually being scraped. A dead exporter
makes the rule stop firing, Alertmanager stops posting to the ping URL, and the
alarm is raised by Healthchecks, **outside the machine**. Detection moves out of
the monitoring without adding a category.

One silence therefore attests seven things at once: the host, k3s,
VictoriaMetrics, vmalert, Alertmanager, `node_exporter`, and outbound
networking. What is given up is the differential diagnosis, since the silence
does not say which of the seven fell. The archive priced that trade and it still
holds: the distinction takes ten seconds once someone is awake, while an
undetected failure lasts days.

Two carriers from the archive were re-judged and both lose to the Watchdog. A
k3s `CronJob` running `curl` attests the host, k3s and the scheduler, but not
the observability stack the alerts actually flow through, so it would leave a
dead Alertmanager undetected. A systemd timer on the host would keep pinging
cheerfully while k3s is dead.

## Cadence: 15 minutes, with 45 minutes of grace

The Watchdog route posts every **15 minutes**; the Healthchecks check is
configured with a 15-minute period and a **45-minute grace**, so a broken chain
is known within roughly an hour.

That is sized against what it watches rather than against a reflex. #11 sets a
72-hour RTO, and ADR-0010 keeps the photo originals on the NAS, so a dead server
loses no data while it is down. An hour of detection latency is nothing against
that. In the other direction, a short grace makes the phone ring for an ordinary
ISP outage, and the documented end state of that is a silenced notification,
which ADR-0004 names as the worst thing that can happen to an alert set.

The free tier pushes the same way. At 100 log entries per check, a five-minute
heartbeat holds about eight hours of ping history and a fifteen-minute one holds
about twenty-five. A faster heartbeat would buy minutes of detection and pay for
them with a night's worth of forensics.

## Three checks, and ADR-0004's third category finally gets a source

Healthchecks holds **three** checks, not one:

1. the Watchdog heartbeat above,
2. the **daily PostgreSQL dump** (ADR-0012),
3. the **monthly automated restore verification** (ADR-0012).

The second exists because reading ADR-0004 against the accepted set exposed the
same hole ADR-0017 found under the disk alert: **"backup has not succeeded
within its RPO window" had no source either.** No accepted ADR publishes a
restic metric, and ADR-0017 explicitly refused the textfile collector that would
have manufactured one. A check-in service closes it for no code at all, since
the `CronJob` pings its own check and its **silence is the alert**. The third
check applies the same treatment to ADR-0012's monthly restore verification,
which is exactly the kind of automated job whose failure is otherwise silent.

This **amends ADR-0004 on the mechanism of its third category, not on its
existence**. The count stays at five, and detection moves outside the machine,
which is the same property the witness was brought in for.

## Routing, and where Alertmanager runs

**One route, one topic, all five categories**, with ntfy's `priority` and `tags`
derived from alert labels by the templated payload. A side effect worth
recording: ADR-0017 accepted that "the notification alone does not say which
sensor spoke" when it merged CPU and NVMe over-temperature into one category. A
templated payload refunds that for free, because the sensor label lands in the
title.

**Alertmanager runs in-cluster**, described by Flux like everything else.
ADR-0004 left this open, writing "systemd `MemoryMax=` or a container memory
limit" without choosing between them, and this ADR has to choose because the
credentials depend on it: ADR-0009's only accepted mechanism is SOPS+age
decrypted by Flux's kustomize-controller, which is **cluster-only**. An
Alertmanager on the host would need a host-side secret mechanism that no
accepted ADR describes, and inventing one to deliver a topic name would be a
large decision made for a small reason.

Both credentials, the **ntfy topic** and the **Healthchecks ping URLs**, are
therefore SOPS+age secrets reconciled by Flux, the same pattern ADR-0011 already
uses for the Cloudflare API token and the Tailscale auth key, and satisfying the
no-CI-secret rule by construction. **Nothing lands on the host**: ADR-0017's
`node_exporter` stays the only host-side occupant of this design and it needs no
credential at all.

The topic then exists in three places, and this is named rather than hidden:
encrypted in this repository, in clear inside the Healthchecks account, and on
the phone.

## One channel, no fallback, and what breaks when the free tier changes

A second channel was considered and refused on the archive's argument, which
survives re-judging: a duplicated alert is a less meaningful alert, and the
habit that forms is ignoring one of the two.

The ticket asked what stops working the day a service stops being free, so it is
written plainly:

- **If ntfy stops being free or disappears**, alerts stop notifying. Healthchecks
  still knows the chain is alive, but nothing reaches the phone. The replacement
  is a URL and a topic in one pull request, because the mechanism is a POST.
- **If Healthchecks stops being free or disappears**, the witness is gone and
  the platform returns to exactly the hole this ADR closes: the chain can die in
  silence, and the daily dump and monthly restore verification lose their
  detector with it. The replacement is another ping URL in one pull request.
- **ntfy's public instance publishes no figure for its daily message quota**,
  only that a per-visitor daily limit exists. Five alert categories and one
  witness are nowhere near any plausible bound, but the bound itself is
  undocumented, so it cannot be checked in advance.

Portability is the reason both were chosen, not a consolation. Neither is
holding state this platform depends on; each is one outbound HTTP call.

## Decision

**ntfy.sh is the receiver.** Alertmanager posts to it from a single
`webhook_config` with a templated `payload` rendering ntfy's JSON publish
schema, needing no adapter and no extra process. One route, one topic, all five
categories, priority and tags carried from alert labels. The topic is a secret.

**Healthchecks.io, free tier, is the witness**, notifying through its native
ntfy integration onto the same topic. It holds three checks: the Watchdog
heartbeat, the daily PostgreSQL dump, and the monthly restore verification. Ping
period 15 minutes, grace 45 minutes.

**The Watchdog's expression is anchored on a `node_exporter` metric** rather
than on `vector(1)`, so a dead collector silences the heartbeat and is caught
from outside, closing ADR-0017's dependency without a sixth alert category.

**Alertmanager runs in-cluster.** Both credentials are SOPS+age secrets
reconciled by Flux; nothing touches the host.

Exact PromQL, the payload template and the Alertmanager route tree are
implementation, as ADR-0004 and ADR-0017 both established for their own rules;
the cadence, the grace and the check count above are not.

## Alternatives rejected

**Email via `email_config`.** Zero new accounts and a searchable archive.
Rejected because Alertmanager would have to speak SMTP, which means one more
application password, and above all because an alert drowned in an inbox is read
when someone thinks to look, not when it fires.

**A Telegram bot via `telegram_config`.** Natively supported, templatable and
widely used in homelabs. Rejected for a bot token and a chat ID in secrets where
an ntfy topic needs neither.

**Discord via `discord_config`.** Natively supported and needs only a webhook
URL. Rejected on the same terms as Telegram, with an account added on top, for
no gain over a topic name.

**Pushover via `pushover_config`.** The best native fit of the paid options,
templatable with an emergency priority. Rejected because it costs money once per
platform, and #29 rules out paying for what this platform can do for free.

**Collapsing everything onto Healthchecks.io**, with Alertmanager posting to a
check's `/fail` endpoint so only one third party exists. Genuinely tempting, and
rejected because Healthchecks is a check-in service: Alertmanager's grouping and
inhibition, the single reason ADR-0004 chose it over Grafana-managed alerting,
would come out flattened into a ping body.

**A self-hosted ntfy, or a self-hosted Healthchecks.** Both are open source and
both would keep every byte in the house. Rejected structurally rather than on
cost: each would die with the machine it watches, at the exact moment the alert
matters.

**A Cloudflare Worker on a cron trigger.** Cloudflare is already an accepted
dependency under ADR-0011 and the free plan includes scheduled triggers.
Rejected for the archive's reason, re-checked and still true: a Worker probes
what answers, which makes it a fine external probe and a poor heartbeat
receiver, since the state, the lateness and the notification would all be
home-made code to write and maintain.

**A self-hosted witness on a VPS.** Total control and no data at a third party.
Rejected for the recurring cost and the extra machine, exactly as ADR-0011
rejected the paid VPS relay and #29 rejected paid hosting generally.

**An `absent()` rule on `node_exporter`.** The obvious way to detect a dead
collector, already rejected by ADR-0017 and not revived here: it watches the
monitoring from inside the monitoring, and it would cost a sixth alert category.
Anchoring the Watchdog on an exporter metric obtains the same detection from
outside, for nothing.

**A k3s `CronJob` running `curl` as the heartbeat.** The archive's own first
slice, and cheaper in moving parts. Rejected because it attests the host, k3s
and the scheduler while saying nothing about VictoriaMetrics, vmalert or
Alertmanager, so the alerting chain could be dead with the heartbeat still
beating.

**A systemd timer on the host as the heartbeat.** The shortest and most robust
path, independent of k3s. Rejected because it would keep pinging cheerfully
while k3s is down, producing no silence and therefore no alert.

**A five-minute heartbeat.** Faster detection, and the reflex answer. Rejected
because there is nothing to do with the extra fifty minutes against a 72-hour
RTO on a machine whose data lives on the NAS, and because it would cut the free
tier's ping history to about eight hours while raising the odds of being woken
by an ISP blip.

**A second notification channel behind the first.** Robust if one falls.
Rejected on the archive's argument, re-judged and still standing: two channels
make each alert less meaningful, and one of them ends up ignored.

**Leaving ADR-0004's third category without a source**, deferred to the ticket
that builds the backup job. The smallest change, and rejected because the
witness is being stood up in this ADR anyway, a second check costs one `curl` in
a `CronJob` ADR-0012 already requires, and the alternative source was the
textfile collector ADR-0017 had just refused.

## Consequences

- **ADR-0004's alert set is amended a second time.** ADR-0017 changed its count;
  this ADR changes the mechanism of its third category, which now reports by
  silence to an external check-in service rather than by a rule evaluated
  against a metric nothing publishes.
- **ADR-0017's dependency is closed.** Its five categories have a destination,
  and a dead `node_exporter` is now caught from outside the machine.
- **ADR-0004's open question about where the observability stack runs is
  settled for Alertmanager**: in-cluster, under Flux. The other three
  components are not decided here, and the split's cgroup enforcement is
  unchanged either way.
- **Alertmanager must be 0.32.0 or newer.** The adapter-free path depends on
  webhook payload templating, which does not exist before that release. Pinning
  it is the installing ticket's job; running an older Alertmanager silently
  reintroduces either an adapter process or an unreadable JSON notification.
- **Two free third-party tiers are now load-bearing for every alert this
  platform raises**, with no fallback channel. Both are replaceable by a URL in
  a pull request, and neither can be replaced by a self-hosted equivalent.
  Recorded in `docs/reference/risk-register.md`.
- **The ntfy topic exists in clear inside the Healthchecks account**, outside
  this repository's SOPS+age control, as a consequence of routing the witness
  through the same channel as the alerts.
- **Detection of a broken chain takes up to about an hour**, by choice. Between
  the failure and the notification nobody is warned, and ADR-0017's thermal
  alert is one of the things not being delivered during that window.
- **Nothing here covers the NAS.** ADR-0011 leaves the DS412+ without a route to
  the internet, so it cannot notify anyone by itself, and no check in this
  design watches it. The photo corpus's sole-copy risk keeps the register entry
  it already has, and gains no detector from this ADR.
