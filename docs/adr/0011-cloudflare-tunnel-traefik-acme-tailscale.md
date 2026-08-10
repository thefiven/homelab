---
status: accepted
date: 2026-08-10
tags: [networking, security, exposure]
---

# Cloudflare Tunnel for public exposure, Traefik-native ACME, Tailscale for private access

#22 asked four coupled questions at once: how services reach the internet, how ingress and
certificates work, how private access is granted, and what segmentation buys on hardware that
can't really do it. #8's measured ~100 Mbit/s upstream ceiling and the platform's standing
no-CI-secret rule (reconciliation is pulled from inside the network; nothing pushes credentials
in) bound every answer below. An earlier, single-machine iteration of this project answered a
near-identical question in its own ADR-0006. That decision is re-judged from zero here, per the
map's standing rule, rather than deferred to. It turns out to still hold, but for reasons checked
fresh, not inherited.

## Exposure posture

Immich stays **private-only**, reachable only over the VPN, never through the public tunnel.
Three independent reasons hold this, none of them new: a young, fast-moving codebase's CVE
surface; Cloudflare's proxy body-size limit (below); and the ToS risk of transiting a large media
library through a CDN not licensed for it (below). The two web stacks in development are
showcase-shaped and go **public** through the tunnel; no current workload needs an invite-only
gate (the old project's `kalenjin`-style Cloudflare Access barrier has no counterpart here today).
Any future, not-yet-known service defaults to **private** until a ticket argues it out. The
cheaper failure mode is a family member opening Tailscale, not private data facing the internet
by default.

## Public exposure: an outbound tunnel, on Cloudflare

Port-forwarding 80/443 on the router plus dynamic DNS is rejected outright, as it was last time:
it makes the residential IP public and linkable. An **outbound-only tunnel** avoids that
entirely and needs no port ever opened. **Cloudflare** is the provider: free, and its DNS-01
challenge is what the wildcard certificate below needs.

Two limits were checked fresh rather than assumed from the old ADR
(`docs/reference/research-ingress-and-public-exposure.md`, §1-2):

- **100 MB max request/response body** on Free and Pro plans
  ([developers.cloudflare.com/cache/concepts/default-cache-behavior](https://developers.cloudflare.com/cache/concepts/default-cache-behavior/)).
  Not published for Tunnel by name; Tunnel hostnames are proxied at the same edge as any other
  zone, so this is the number to plan against, but it is an inference from two pages agreeing,
  not one page naming Tunnel.
- Cloudflare's Service-Specific Terms restrict serving "a disproportionate percentage of
  pictures, audio files, or other large files" through the CDN without its paid media services
  ([cloudflare.com/service-specific-terms-application-services](https://www.cloudflare.com/service-specific-terms-application-services/)).
  The dedicated Zero Trust/Tunnel terms don't repeat this clause or name Tunnel at all, a gap
  the old ADR's citation didn't have, but nothing establishes Tunnel is exempt from it either, so
  the conservative reading stands.

Neither limit moves where Immich lives; it was already excluded on CVE-surface and ToS-risk
grounds independent of the byte count. They do confirm the two showcase web stacks, not
media-serving, are the only things that should ever cross this tunnel.

## Ingress and ACME: Traefik's own, no cert-manager

k3s already installs Traefik as its default ingress controller (ADR-0007); swapping it for Caddy
or ingress-nginx has no stated reason and was not pursued. The open question was cert-manager
versus Traefik's built-in ACME, and it resolves in Traefik's favour: both support a Cloudflare
DNS-01 wildcard certificate with no caveat
(`docs/reference/research-ingress-and-public-exposure.md`, §4-5), and the current k3s `stable`
channel (v1.36.3+k3s1) bundles Traefik v3.7.8, which inherits Cloudflare DNS-01 support
transitively through the Lego library it delegates to, with no version gate documented anywhere.

The one initially-plausible reason to prefer cert-manager, that its cluster-visible
`Certificate`/`Secret` gives the "certificate expiring soon" alert ADR-0004 already commits to
where Traefik's file-based `acme.json` might not, does not survive a check: Traefik publishes its
own `traefik_tls_certs_not_after` Prometheus metric for every certificate it holds, ACME or not,
in the same shape the alert needs (`(traefik_tls_certs_not_after - time()) < threshold`). With
that gap closed, nothing on this platform needs a certificate outside Traefik, so cert-manager's
actual advantage, letting some other workload reuse the same cert via a Kubernetes `Secret`, has
no current buyer. It stays out: one fewer controller to install, upgrade, and track in Flux, for
a reusability need nothing has today.

The wildcard itself answers the ticket's inherited concern from #25's publication policy: a
publicly-issued certificate publishes every hostname it covers to Certificate Transparency logs
regardless of what the repository does or doesn't say, so hostnames can never be secret by
omission. A wildcard cert is the mitigation against subdomain enumeration this makes available.
It is an ACME configuration choice, not a repository one, and it is now the plan.

## Private access: Tailscale

Tailscale again, for the same reason as last time and checked fresh: non-technical family
members install it once and it stays out of their way, where plain WireGuard needs a
hand-configured peer per device. #10's two family Immich accounts are still the users this
serves. Tailscale's Personal/Free plan, repriced 2026-04-08, permits up to 6 users and
**unlimited devices**, no device cap at all under the current terms
([tailscale.com/pricing](https://tailscale.com/pricing);
`docs/reference/research-ingress-and-public-exposure.md`, §3), comfortably above what a
single-operator homelab with two family accounts needs.

The old project's fallback, a ~55 €/year VPS relay with a WireGuard tunnel kept on standby in
case Tailscale proved painful for the family, is **dropped outright**, not carried forward as
contingency language. #29 already forbids paid hosting for any workload beyond the seedbox; a
documented fallback that already contradicts a standing decision is a landmine for whichever
future session reaches for it without re-checking #29, not a real option.

## Segmentation: stated plainly, not solved

The office switch is unmanaged: no VLAN, no LACP, no port mirroring, unchanged since the archived
project measured it. The isolation trick that project used for the NAS, no gateway and no DNS
configured on the device itself so nothing routes out and nothing from the internet can route in,
is carried forward as-is, because the hardware fact it rests on is identical, not stale. Stated
plainly, per the ticket's own instruction: **this buys isolation from the internet, and nothing
else.** Any device already on the LAN can still reach the NAS; only the NFS export rule (naming
one address, not the /24) narrows that further, and it is configuration, not topology, a rule
widened later would silently undo the isolation with nothing to flag it. Real segmentation needs
a managed switch this platform doesn't have.

## No-CI-secret compliance

Both credentials this decision introduces, the Cloudflare API token Traefik's DNS-01 solver
needs and Tailscale's node auth key, are SOPS+age-encrypted in the repository (ADR-0009) and
reconciled by Flux (ADR-0008) from inside the cluster. Neither is ever held by CI. This is not a
new mechanism; it is the already-adopted pull-based architecture applied to two more secrets,
which is what makes the ticket's constraint satisfied by construction rather than by a new
argument.

## Decision

**Cloudflare Tunnel** carries the two public web stacks; Immich stays reachable only over
**Tailscale**. Ingress is k3s's bundled **Traefik**, terminating TLS itself via built-in ACME
DNS-01 against Cloudflare, issuing one **wildcard certificate**, no cert-manager. The unmanaged
switch gets no VLAN; the NAS keeps the no-gateway/no-DNS isolation trick, documented for what it
does and doesn't buy. The old paid VPS+WireGuard relay fallback is dropped. Both new credentials
(Cloudflare API token, Tailscale auth key) are SOPS+age secrets reconciled by Flux, never a CI
push.

## Alternatives rejected

**Port-forward 80/443 + DDNS on the router.** Publishes the residential IP and ties it to the
domain; eliminated without further comparison, as before.

**Cloudflare Tunnel for Immich too.** The simplest single-mechanism design, rejected on three
independent grounds: CVE surface of young, actively-developed software facing the internet;
Cloudflare's 100 MB proxy body limit, which breaks ordinary phone-video uploads; and the ToS risk
of transiting a media-heavy library through a CDN not licensed for large-file serving.

**cert-manager.** Functionally equivalent to Traefik-native ACME for this decision (same
Cloudflare DNS-01 wildcard support), and would make certificates reusable by other workloads, a
need nothing here has, at the cost of a second controller to install, upgrade, and GitOps-track.
The one concrete reason to prefer it, covering ADR-0004's certificate-expiry alert, turned out to
already be covered by Traefik's own `traefik_tls_certs_not_after` metric.

**Plain WireGuard instead of Tailscale.** Technically sufficient, but pushes per-device peer
configuration onto non-technical family members; Tailscale's free tier removes any reason to pay
that ergonomic cost.

**Keeping the VPS+WireGuard relay as a documented fallback.** Real prior art, but it now
contradicts #29's no-paid-hosting rule outright; keeping it as "contingency" language would only
plant a future violation instead of preventing one.

**A VLAN or other switch-level segmentation.** Not achievable on the unmanaged switch this
platform actually has; documented as a gap rather than worked around, since no software
substitute changes what the hardware can't do.

## Consequences

- **The Cloudflare API token and Tailscale auth key still need their one-time bootstrap**, the
  same shape as ADR-0009's SOPS bootstrap step, once a cluster exists to load them into. Out of
  scope for this map; left to whichever future ticket installs the platform.
- **Traefik's certificate-resolver configuration (`dnsChallenge: provider: cloudflare`,
  `storage: acme.json`) is not written here.** Per the map's standing rule against configuration
  before the ADR it derives from is accepted, that belongs to the installing ticket.
- **Choosing Traefik-native ACME over cert-manager means certificates are trapped in Traefik's
  `acme.json`.** If a future workload needs the same certificate independently of Traefik (a mail
  server, a second ingress controller), this decision does not serve it; revisit cert-manager then
  rather than retrofitting reuse onto a file store that doesn't support it.
- **The domain name(s) themselves, thematic vs. umbrella, registrar, actual purchase, are not
  decided here.** This ADR settles the mechanism; naming and acquisition are operational tasks for
  a future ticket.
- **Real network segmentation remains an open gap**, not a deferred assumption: it reopens only if
  the switch hardware changes, which nothing here schedules or requires.
