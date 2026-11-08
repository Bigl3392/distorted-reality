# Deployment artifacts — prepared, not executed

Classification: DevOps documentation; application/runtime layers.
These are text for a separately authorized operator review. No host was contacted, installed, provisioned or activated.

## Gates and unresolved inputs

- G3: `<<G3_SUBDOMAIN>>` is unresolved. No public URL is invented.
- G4: `<<G4_DOCKER_VERSION>>`, the reviewed base digest and built-image digest are unresolved.
- G8: `<<G8_PLAN_REGION_OS>>` and console pricing remain unresolved. No compute purchase is prepared as an executable API call.
- The API entry point, app port, runtime paths, SSH operator source and approved command deadlines must come from the corresponding owners.
- Token/rate limits, model settings and the first live measurement remain separately controlled. These templates do not enable operator inference.
- All `<<...>>` placeholders must be replaced by reviewed inputs. The renderer rejects every unresolved token.
- Do not install until explicit authorization covers the exact host and action. Reading or rendering these files grants none.

## Text inventory

`Render-Plan.ps1` prompts for a template directory, its expected manifest digest and destination. Dry-run is the default; it renders in memory only. It never connects to a host. Use PowerShell 7 (right-click launch relaunches in pwsh 7 and pauses).
`control.nft.in` and `sandbox.nft.in` define separate default-drop ingress/egress policies. Render numeric addresses explicitly; inspect the entire candidate before a future `nft -c` and separately authorized application.
`app.service.in` uses an operator-supplied interpreter/entry point and systemd EnvironmentFile; there is no credential in unit text or user-data.
`Caddyfile.in` supplies HTTPS reverse-proxy text, pending actual domain/port.
`docker-channel.in.sh` is a restricted SSH forced command for C→S Docker transport.
`docker-install.in.sh` is an operator-reviewed installation template, never executed here.
M4 owns `sandbox/dr-reaper.service.in`, `sandbox/dr-reaper.timer` and `sandbox/reaper.py`; refer to those exact files rather than maintaining a second implementation.

## Host review sequence (future authorization only)

1. LDR verifies plan, region, OS, price and two distinct host identities in the console.
2. Confirm a recovery console and preserve existing firewall configuration. Never flush an unknown ruleset.
3. Confirm SSH access from the named operator source to C, and only from C to S. S has no public application listener.
4. Bootstrap the approved Docker repository while the host is under operator control; choose exact engine, CLI, containerd and plugin package versions. Do not use a convenience install pipe.
5. Install only explicitly pinned packages and record client/server `docker version`. Verify base and built-image digests independently. No image/version lock has been created by this module.
6. S has no inference credential, deploy credential, ground truth or journal. The runner Docker group is root-equivalent on S; the restricted SSH transport does not turn Docker into a fine-grained permission boundary.
7. C holds a root-owned mode-0600 environment file. LDR creates it outside source, backups, terminal recording and user-data. Never request its contents in chat. Root systemd reads EnvironmentFile before dropping to the app user. Supply only approved model/limit settings.
8. The C→S SSH key is scoped to S and operator-installed mode 0600. S authorized_keys uses `restrict,from="<control-address>",command="<absolute-forced-command-path>"`. The wrapper permits only the exact Docker stdio command. No agent handles a private key.
9. Review firewall drafts, test syntax and retain console recovery before installing. Established traffic is allowed; S permits new inbound SSH only from C and no new outbound sessions. C permits HTTPS, operator SSH and explicit outbound DNS/NTP/HTTPS/S SSH as listed.
10. Install the reviewed reaper on S (also C only for a separately chosen T0 deployment). Replace every unit placeholder first. Do not enable services during preparation.
11. Validate TLS, packet expiry, approval isolation, rate limiting and fallback only after M5/M6 and a separate deployment go.
12. Containment and runaway proofs require their own authorized runs. No host acceptance row is passed by these documents.

## Limitations

No cloud-init/user-data contains a key. There is no automatic ACL, credential or remote mutation here.
Caddy and nftables templates have not been tested on the eventual Ubuntu image. IPv6 source policy, DNS/NTP endpoints, Docker SSH transport and the final systemd unit need host-specific review.
A root mode-0600 env file is read by systemd, not by a non-root process opening it directly.
No plan name, price, region, runtime port, subdomain or package version is asserted.
