# Ingress and public exposure: Cloudflare Tunnel limits, Tailscale free tier, and ACME DNS-01 options

**Date:** 2026-08-10
**Status:** Research note. No decision is made here.
**Method:** Primary sources only: official Cloudflare, Tailscale, cert-manager, Traefik and k3s
documentation, official pricing pages, and upstream release notes. Every claim carries a direct
URL. Where a primary source does not answer the question, this note says so rather than
substituting an estimate.

Context this note is written against: k3s is the chosen orchestrator (ADR-0007) and bundles
Traefik as its default ingress controller. Flux is the GitOps engine (ADR-0008), pull-based only,
no CI secret may exist for this platform. SOPS+age is the secret mechanism (ADR-0009). The
platform has a hard 32 GB RAM ceiling and a measured ~100 Mbit/s upstream bandwidth ceiling on
any leg that crosses public internet or VPN.

---

## 1. Cloudflare Tunnel + Free/Pro: maximum upload (request body) size

Cloudflare publishes a single per-plan table for this, reached from two different documentation
trees that agree with each other:

| Plan | Maximum upload size |
|---|---|
| Free | **100 MB** |
| Pro | **100 MB** |
| Business | 200 MB |
| Enterprise | 500+ MB |

Source: [developers.cloudflare.com/cache/concepts/default-cache-behavior](https://developers.cloudflare.com/cache/concepts/default-cache-behavior/),
under "Maximum upload size", which also states: "Customers can reduce the **Maximum Upload Size**
from the zone's **Network** page", i.e. the number in the table is a ceiling, and it can only be
lowered by the zone owner, not raised, below Enterprise.

The same figures are repeated on the troubleshooting page for the error this limit produces:
"The `413 Payload Too Large` status code indicates that the server refuses to process the request
because the payload sent by the client exceeds the server's acceptable size limit", with the
identical Free/Pro/Business/Enterprise table, last updated 2026-04-23
([developers.cloudflare.com/support/troubleshooting/http-status-codes/4xx-client-error/error-413](https://developers.cloudflare.com/support/troubleshooting/http-status-codes/4xx-client-error/error-413/)).
Cloudflare's connection-limits reference page points to the Cache page as the authority for this
number rather than restating it itself
([fundamentals/reference/connection-limits](https://developers.cloudflare.com/fundamentals/reference/connection-limits/)).
That same page separately states request and response headers are each capped at 128 KB and URLs
at 16 KB, not the constraint here, but adjacent limits worth knowing.

**On Enterprise, the limit is raisable, not unlimited:** "Enterprise customers can contact their
account team or Cloudflare Support for a higher request body limit", so the 500+ MB figure is a
floor for that plan, not a hard cap.

**Tunnel-specific figure: not separately published.** Neither
[developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel](https://developers.cloudflare.com/cloudflare-one/networks/connectors/cloudflare-tunnel/)
nor its sibling pages state a Tunnel-specific body-size limit. The Tunnel docs describe the
connector's job as sending "traffic to the nearest Cloudflare data center" over an outbound-only
connection, but do not say explicitly whether that traffic is then subject to the same zone-level
proxy limits as ordinary orange-clouded DNS records. Cloudflare Tunnel routes a proxied hostname
through Cloudflare's edge exactly as any other proxied zone does; there is no separate ingress
path documented, so the 100 MB Free/Pro figure is the number to plan against, but this is an
inference from the two pages agreeing rather than a single page stating it for Tunnel by name.

**What this means for the stated use case:** a 100 MB ceiling makes ordinary phone-shot video
(typically several hundred MB to a few GB for anything beyond a short clip) fail through the
proxy on Free or Pro. The only first-party ways around it, per the troubleshooting page, are:
chunked/resumable upload from the client, serving that one hostname DNS-only (grey-clouded, no
proxy, no Tunnel), or upgrading to Business (200 MB) or Enterprise (raisable on request).

---

## 2. Cloudflare's terms on serving/transiting large media through the CDN

Cloudflare's **Service-Specific Terms** contain a clause captioned "Content Delivery Network
(Free, Pro, or Business)". The parenthetical itself is the scoping: it does not apply to
Enterprise.

> "Unless you are an Enterprise customer, Cloudflare offers specific Paid Services (e.g., the
> Developer Platform, Images, and Stream) that you must use in order to serve video and other
> large files via the CDN."
>
> "Cloudflare reserves the right to disable or limit your access to or use of the CDN, or to
> limit your End Users' access to certain of your resources through the CDN, if you use or are
> suspected of using the CDN without such Paid Services to serve video or a disproportionate
> percentage of pictures, audio files, or other large files."

Source: [cloudflare.com/service-specific-terms-application-services](https://www.cloudflare.com/service-specific-terms-application-services/),
last updated 2026-06-02.

Cloudflare's own explanatory docs page confirms the intent and history, and drops the older
literal "HTML vs. non-HTML" framing in favour of this "disproportionate" test:

> "From the beginning, we prohibited streaming video content using our bandwidth." "Every second
> of a typical video requires as much bandwidth as loading a full web page." "If your application
> appears to be serving videos or a disproportionate amount of large files without using the
> appropriate paid service, Cloudflare may redirect your content."

Source: [developers.cloudflare.com/fundamentals/reference/policies-compliances/delivering-videos-with-cloudflare](https://developers.cloudflare.com/fundamentals/reference/policies-compliances/delivering-videos-with-cloudflare/),
last updated 2026-04-20.

The permitted alternative is to host the media on a Cloudflare-owned service (Stream, Images, R2)
and let the CDN front that, or to serve the large-file hostname DNS-only (grey-clouded, outside
the CDN and outside this clause), the same escape hatch as §1.

**Zero Trust / Tunnel-specific terms: no separate media clause found.** The dedicated
[cloudflare.com/service-specific-terms-zero-trust-services](https://www.cloudflare.com/service-specific-terms-zero-trust-services/)
document does not mention Cloudflare Tunnel by name and contains no video/large-file/predominant-
use restriction; its only quantified limit is unrelated ("Cloudflare Gateway DNS only is subject
to an Average Monthly DNS Queries limit of 150,000 per Seat"). **Not established from primary
sources:** whether Cloudflare treats a Tunnel-proxied hostname as "the CDN" for purposes of the
Application Services clause above. Given Tunnel hostnames are ordinary proxied DNS records at the
edge (§1), the more conservative reading, that the CDN clause applies to them too, is the one to
plan against, but no Cloudflare document states this for Tunnel by name.

---

## 3. Tailscale Personal/Free plan: device and user caps

Tailscale overhauled its pricing on 2026-04-08. Current terms, from the pricing page itself:

- **Users:** "Up to 6 users" on the Personal plan
  ([tailscale.com/pricing](https://tailscale.com/pricing)).
- **Devices:** "Unlimited user devices", no device-count cap
  ([tailscale.com/pricing](https://tailscale.com/pricing)).
- **Price:** free indefinitely. The announcement: "the Personal plan is getting better and staying
  free. It now supports up to six users, the same limit Personal Plus had" ... "one Personal plan,
  free, with more included by default" ... "The new pricing is live now"
  ([tailscale.com/blog/pricing-v4](https://tailscale.com/blog/pricing-v4), 2026-04-08).
- **Corroborating docs page:** "The Personal plan permits 6 free users in a single Tailscale
  network, known as a tailnet"
  ([tailscale.com/docs/account/manage-plans/free-plans-discounts](https://tailscale.com/docs/account/manage-plans/free-plans-discounts)).
- Two smaller caps also on the pricing page, not asked for but adjacent: "Up to 50 tagged
  resources to start" (extra ones are $1/month each), and "1,000 mins per month for ephemeral
  resources" (short-lived workloads such as CI/CD runners or Kubernetes pods).

This replaced the prior Personal plan, which was capped at 3 users and 100 devices. The device
cap is gone entirely under the new terms, and the user cap moved from 3 to 6. For a single-operator
homelab, neither the 6-user nor the "unlimited devices" figure is a binding constraint.

---

## 4. cert-manager: Cloudflare DNS-01 wildcard support

**Yes, with no documented caveat specific to wildcards.** cert-manager's general DNS validation
tutorial states plainly:

> "You can obtain certificates for wildcard domains just like any other. Make sure to wrap
> wildcard domains with asterisks in your YAML resources, to avoid formatting issues."

Source: [cert-manager.io/docs/tutorials/acme/dns-validation](https://cert-manager.io/docs/tutorials/acme/dns-validation/).

That page's worked example issues a certificate covering both `*.example.com` and `example.com`
from a single `Certificate` resource, using Cloudflare as the configured DNS01 solver on the
`Issuer`. The Cloudflare-specific provider page does not repeat the wildcard statement (it has no
wildcard-specific caveat at all) but documents two things that do matter operationally:

- **Two auth modes**, API Token (recommended, scoped) or API Key (account-wide): "API Tokens allow
  application-scoped keys bound to specific zones and permissions, while API Keys are
  globally-scoped keys that carry the same permissions as your account." Token permissions needed:
  "Zone - DNS - Edit" and "Zone - Zone - Read."
- **A TLD blocklist inherited from Cloudflare itself, not from cert-manager:** "Cloudflare blocks
  the use of the API to update DNS records for the following TLDs: `.cf`, `.ga`, `.gq`, `.ml` and
  `.tk`", irrelevant unless the platform's domain sits on one of those TLDs.

Source: [cert-manager.io/docs/configuration/acme/dns01/cloudflare](https://cert-manager.io/docs/configuration/acme/dns01/cloudflare/).

Since a wildcard cert can only ever be issued via DNS-01 (see §5, Traefik docs, which states the
same Let's Encrypt-level rule), and cert-manager's Cloudflare solver is a DNS-01 solver with no
documented wildcard exclusion, wildcard issuance against this domain is supported.

---

## 5. Traefik-native ACME DNS-01 vs. cert-manager, and what the current k3s bundles

### 5.1 Does Traefik's built-in ACME do DNS-01 against Cloudflare's API, without cert-manager?

Yes. Traefik's own ACME reference page documents a `dnsChallenge` mode on a certificate resolver:

```yaml
certificatesResolvers:
  myresolver:
    acme:
      email: your-email@example.com
      storage: acme.json
      dnsChallenge:
        provider: cloudflare
```

Traefik does not implement each DNS provider itself: "Traefik relies internally on
[Lego](https://go-acme.github.io/lego/) for ACME. You can find the list of all the supported DNS
providers in their [documentation](https://go-acme.github.io/lego/dns/) with instructions about
which environment variables need to be setup."

Source: [doc.traefik.io/traefik/reference/install-configuration/tls/certificate-resolvers/acme](https://doc.traefik.io/traefik/reference/install-configuration/tls/certificate-resolvers/acme/).

Lego's own Cloudflare provider page confirms the provider code and credentials needed: provider
name **`cloudflare`**, and either `CF_DNS_API_TOKEN` (scoped token, recommended) or the legacy
`CF_API_EMAIL` + `CF_API_KEY` pair (account-wide key), plus optional `CLOUDFLARE_*` tuning
variables (`_POLLING_INTERVAL`, `_PROPAGATION_TIMEOUT`, `_TTL`, etc.), all of which can be
suffixed `_FILE` to read from a file instead of an inline value
([go-acme.github.io/lego/dns/cloudflare](https://go-acme.github.io/lego/dns/cloudflare/)).

Same Traefik ACME page also confirms wildcard support natively: "ACME v2 supports wildcard
certificates," "wildcard certificates can only be generated through a DNS-01 challenge," and notes
one real limitation: "It is not possible to request a double wildcard certificate for a domain
(for example `*.*.local.com`)", not relevant to a single wildcard per zone.

### 5.2 What is given up by choosing Traefik-native ACME over adding cert-manager

This is a trade-off, not a documented recommendation from either project; what follows is what the
primary sources establish about the shape of each option, not a verdict.

**Storage model.** Traefik-native ACME persists certificate state in a single file, `acme.json`
by default (`storage: acme.json` in the example above), not a Kubernetes `Secret`, not a CRD.
cert-manager's model is Kubernetes-native throughout: `Certificate`/`Issuer`/`ClusterIssuer` CRDs,
with the resulting cert written to an ordinary `Secret` that any workload (not just the ingress
controller that requested it) can mount. Traefik's file-based store means only Traefik can see or
reuse a certificate it obtained; anything else on the cluster needing the same cert (a non-Traefik
service, a mail server, etc.) cannot reuse it without cert-manager.

**Maintenance surface.** Traefik-native ACME adds zero components: it is configuration on the
ingress controller that is already there (k3s bundles Traefik by default, see §5.3). cert-manager
is a separate controller that must be installed, upgraded, and reconciled on its own cadence, with
its own CRDs, its own webhook, and its own Flux `HelmRelease`/Kustomization to track. For a
single-operator 32 GB platform this is a real extra moving part; the primary-source trade is
"one more component to own" versus "certs are trapped inside Traefik's file and not
cluster-visible."

**Wildcard support.** Neither loses on this axis: both support Cloudflare DNS-01 wildcard
issuance per §4 and §5.1 above.

### 5.3 Does the current stable k3s release's bundled Traefik support Cloudflare?

**Current k3s `stable` channel, per k3s's own channel-server API, is `v1.36.3+k3s1`**
([update.k3s.io/v1-release/channels](https://update.k3s.io/v1-release/channels), machine-readable
JSON: `{"id":"stable", ..., "latest":"v1.36.3+k3s1"}`).

That release's own notes and its GitHub release page both give the embedded component version:
**Traefik v3.7.8**, via the Traefik Helm chart line that k3s's v1.36.2+ bumped to v40.x, with one
flagged breaking change unrelated to DNS providers ("the provider name changes from
`kubernetesIngressNginx` to `kubernetesIngressNGINX`")
([docs.k3s.io/release-notes/v1.36.X](https://docs.k3s.io/release-notes/v1.36.X);
[github.com/k3s-io/k3s/releases/tag/v1.36.3+k3s1](https://github.com/k3s-io/k3s/releases/tag/v1.36.3%2Bk3s1),
"Embedded Component Versions" table).

**k3s itself does not maintain a "supported DNS providers" list**; that list is Lego's (§5.1),
and Traefik delegates to whatever Lego version ships inside the Traefik binary it embeds. Since
Cloudflare has been a stable, long-supported Lego DNS provider (present continuously across the
Traefik v2 to v3 line per the version history surfaced while researching §5.1, with no version gate
documented anywhere), the bundled Traefik v3.7.8 in the current k3s stable release supports
Cloudflare DNS-01 out of the box, using the same `provider: cloudflare` configuration shown in
§5.1. No version-specific caveat is documented by either k3s or Traefik.

---

## 6. What was not established from primary sources

1. **A Cloudflare document that names Cloudflare Tunnel explicitly** when stating the 100 MB
   Free/Pro body-size limit or the CDN media-restriction clause. Both are stated for "the CDN" /
   proxied zones generally; Tunnel hostnames are proxied through the same edge, but no page ties
   the two together by name (§1, §2).
2. **Whether Cloudflare's Zero Trust / Tunnel-specific Service-Specific Terms carry any
   media-serving restriction of their own.** They do not appear to: the only quantified limit
   found there is the Gateway DNS query cap, unrelated to this question (§2).
3. **A single Traefik or k3s page that states, by version number, "Cloudflare is supported as of
   Traefik vX.Y."** Support is inherited transitively through Lego and is not gated or listed
   per-Traefik-version in any primary source found (§5.3).
