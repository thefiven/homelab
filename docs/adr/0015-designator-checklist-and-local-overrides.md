---
status: accepted
date: 2026-08-12
tags: [repository, documentation, security, privacy, ansible]
---

# Designator checklist and the local-overrides mechanism

## What this extends

ADR-0001 draws the line: nothing that designates this particular installation
is published — hostnames, IP addresses, hardware identifiers, family details,
anything from which the physical location can be deduced. That decision is
unchanged here. What ADR-0001 did not spell out is a mechanism problem: some
of those designators are not narrative, they are what the automation actually
needs to run — a disk serial the `zfs` role must read to pick the right
physical NVMe, an IP address Ansible needs to open an SSH connection, an auth
key a role hands to a running service. ADR-0001's placeholder convention
(`example.com`, `192.0.2.0/24`, generic node names) covers what a reader
sees. It does not say where the real values live so the platform still runs.

This is not hypothetical. #74's hardware bring-up hit three real cases inside
ADR-0001's own five bullets, and surfaced one category the original list did
not name at all.

## What #74 got wrong

Mid bring-up, `ansible/inventory.yml` and `ansible/host_vars/node1.yml` were
renamed from the generic `node1` to the node's real OS hostname —
reasoned at the time as "avoiding drift" between the Ansible alias and the
hostname `build-media --hostname` bakes into the node's install media. That
reasoning was backwards. The Ansible inventory alias and the real OS hostname
were never supposed to match — keeping them apart is ADR-0001's placeholder
convention working as intended, not an inconsistency to fix. The real
hostname now appearing in tracked files (the inventory key, an SSH key
comment) is the most linkable single fact of the three found this session:
if it ever resurfaces in another context — a Tailscale admin console, a
future repository, a resume — it is the connective tissue between this
public repository and a reachable machine, which is exactly the adversary
ADR-0001 names.

The other two: `ansible_host` was set to the node's real LAN IP with its MAC
address in a comment, and `zfs_state_disk_serial` (a real NVMe serial) was
committed in `61664f2`, a session before this one. All three were caught
before merge: `feat/74-node1-bringup`'s history was rewritten so none of the
three ever ship in a tracked file (the original commits remain visible in
the PR's force-push log for anyone auditing the before-state).

## The mechanism: local overrides, not new tracked fields

`ansible/host_vars/*_secrets.yml` already exists, gitignored, holding
`tailscale_authkey` — supplied to `ansible-playbook` via `-e @path` at
run time, never committed, never auto-loaded by Ansible's hostname-matching
convention. That pattern is not specific to credentials. It is the general
answer to "a role needs a real value that must never be in a tracked file":
put it in the gitignored per-node `*_secrets.yml` and pass it with `-e`.

The file keeps its `_secrets` name even now that it carries non-credential
designators (an IP, a disk serial) alongside `tailscale_authkey`. A second
filename split by category was considered and rejected: one gitignore
pattern, one mechanism, is worth more than a naming distinction that changes
nothing about how either kind of value is handled.

## Expanded checklist

ADR-0001's five bullets, widened with what this platform's own roadmap
(ADR-0004, 0007–0014) will concretely produce:

| Category | Concrete future instances | Repo carries | Real value lives |
| --- | --- | --- | --- |
| Hostnames / domains | OS hostnames, Tailscale MagicDNS names, Cloudflare tunnel hostnames, ACME cert CNs, mDNS names | Generic node aliases (`node1`, `node2`, …), RFC 2606 domains | The host itself, Cloudflare dashboard, Tailscale admin console |
| IP addresses / address plans | LAN IPs, WAN/public IP, Tailscale CGNAT addresses (100.64.0.0/10), VLANs, port mappings | RFC 5737 placeholders | Gitignored `host_vars/*_secrets.yml`, passed via `-e` |
| Hardware identifiers | Disk serials, MAC addresses, future nodes' identifiers, GPU/TPM serials, UPS serial | Nothing (no placeholder needed unless a role reads one) | Same gitignored local-overrides file |
| Credentials proper | SOPS+age values (in-cluster), Tailscale authkey, Restic password, Flux deploy key, ACME account key | Nothing, or the encrypted SOPS ciphertext | ADR-0009's SOPS+age flow, or the same `*_secrets.yml` pre-cluster |
| Personal / family | Given names, faces, personal e-mails, Immich accounts, anything drawn from the real photo library | Nothing, ever — not even gitignored | Not automation input; has no reason to be text anywhere versioned |
| Operator's own identity | Git author name/e-mail, GitHub handle | As-is | This is the showcase's byline, a different risk class from family members |
| Location-deducible | ISP name tied to an address, an ultra-specific timezone, a pasted traceroute/WHOIS while debugging | Redacted or generalized before it is ever pasted into a commit, doc, or issue | — |

## Decision

1. Ansible inventory aliases are always generic (`node1`, `node2`, …),
   independent of whatever real OS hostname that node actually has. They are
   not required to match, and are not made to match for consistency.
2. Any value a role needs that is itself a real designator — an IP, a
   serial, a MAC, a real hostname used as data rather than as an inventory
   key — is never written into a tracked `host_vars/*.yml`. It is supplied
   at run time via the node's gitignored `host_vars/<node>_secrets.yml`,
   passed with `-e @path`.
3. A public key's cryptographic material is always publishable (unchanged
   from ADR-0001's `age` key example); a comment or label attached to it is
   a designator like any other and stays generic.
4. Personal and family designators never enter even the gitignored
   local-overrides file. They have no automation role, so they have no
   reason to exist as text anywhere versioned, encrypted or not.
5. The operator's own commit identity is exempt — it is the showcase's
   byline, not something this policy protects against.

## Consequences

Every role that needs a real designator to function now has a named place
for it (`*_secrets.yml` via `-e`) instead of a temptation to just commit the
value "this once." The cost is operational: every real run against real
hardware needs that extra-vars file assembled locally first, by hand, and it
carries a growing, undocumented-in-the-repo set of keys (`tailscale_authkey`
today, `zfs_state_disk_serial` and `ansible_host` after this ADR). Nothing
in the repository enumerates what that file is expected to contain for a
given node — the same "is it a secret?" framing ADR-0001 already rejected
would misclassify half of it. A `*_secrets.yml.example` with commented-out
keys and no values was considered for this and rejected for the same reason
ADR-0001 rejected an inventory of secrets: it would enumerate every
automation-relevant designator this platform uses, in one file, which is
useful to nobody but someone deciding where to start.

## Alternatives rejected

**Loosening ADR-0001 to allow private RFC 1918 LAN IPs and real hostnames
directly in tracked files**, on the reasoning that they carry little
information alone. Rejected: a hostname's risk is not the information it
carries by itself, it is the link it forms if it resurfaces anywhere else,
and the local-overrides mechanism already gets automation working without
paying that cost — loosening the rule would buy nothing.

**A separate `*_local.yml` filename for non-credential designators**,
keeping `*_secrets.yml` strictly for credentials. Rejected: two patterns to
maintain for a distinction that does not change how either file is
gitignored, loaded, or supplied to `ansible-playbook`.
