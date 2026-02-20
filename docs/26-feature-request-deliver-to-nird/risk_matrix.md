Additional Risk Surface Considerations - Local Bitwarden API

Structural effect:

* Vault unlock state = steady-state condition
* Attack window = continuous
* Compromise of seqtech account - immediate vault access

Risk profile for localhost API exposure while vault remains unlocked.

| Threat                                   | Likelihood | Impact   | Risk   |
| ---------------------------------------- | ---------- | -------- | ------ |
| SSH key compromise -> local API access   | Low        | High     | Medium |
| Root compromise -> vault extraction      | Very Low   | Critical | Medium |
| Bitwarden CLI/API vulnerability exposure | Very Low   | High     | Low    |

Focus: localhost API exposure while vault remains unlocked.

Overall residual risk: Medium, dominated by user account integrity.


# Mitigation Mechanisms - Bitwarden Local API While Persistently Unlocked

## 1. Minimize User Blast Radius

* Dedicated upload-only UNIX user
* No interactive shell use for daily work
* No browser, mail client, or dev tools under that UID
* Strict file permissions (0700 home, restricted PATH)
    * This should be enforcable, not advisory: Any access is operationally prohibited and audited.

---

## 2. SSH Hardening

* `AuthenticationMethods publickey` only
* Disable agent forwarding
* Restrict key usage via `authorized_keys` options (`no-port-forwarding,no-X11-forwarding,no-agent-forwarding,no-pty` where possible)
* Hardware-backed SSH key if available

---

## 3. Constrain `bw serve`

* Bind explicitly to `127.0.0.1`
* Restrict listening port via firewall (loopback only)
* Systemd sandboxing:

  * `PrivateTmp=yes`
  * `NoNewPrivileges=yes`
  * `ProtectSystem=strict`
  * `ProtectHome=yes` (adjust carefully)
  * `RestrictAddressFamilies=AF_INET AF_UNIX`

---

## 4. Process Isolation

* Run upload workflow via dedicated systemd user service
* Avoid long-lived login sessions
* Disable user lingering if not required

---

## 5. Reduce Credential Scope

* Use Bitwarden account containing only required secrets
* No unrelated vault items
* Separate organizational vault from personal

---

## 6. Monitoring Controls

* Log API calls from upload process
* Audit SSH logins for upload user
* Alert on unexpected interactive shell sessions

---

## 7. Under Consideration: Vault Unlock Discipline (If Automation Requires Persistent Unlock)

* Unlock immediately before scheduled transfer window
* Lock via script after transfer batch completes
* Optional periodic auto-lock if idle

---

## 8. Root Hardening

* Kernel updates
* Disable unnecessary services
* Enforce SELinux in enforcing mode
* Enable auditd for privilege escalation events

---

Dominant mitigation lever: isolate and minimize trust in the upload user account.


Points to evaluate:

* Is a persistent unlocked vault acceptable given that the real trust boundary is the upload UID?
    To be discussed
* Can the upload UID be made a non-interactive, single-purpose account?
    Already mostly is
* Is localhost TCP required, or can the API surface be removed or reduced?
    The localhost TCP is the fastest way to access to the required authentication tokens, as the unlock happens only once. Accessing the tokens strictly via the command line client can be done but it introduces additional delays, which may impede authentication
* What is the impact if only NIRD secrets exist in that vault?
    access to scientific data
* Is automation frequency high enough to justify permanent unlock vs scheduled unlock windows?
    creating an unlock mechanism is under consideration, but for now yes. Logging in on a Saturday or Sunday to upload files is not justified.
* Would a non-interactive secret backend remove the need for `bw serve` entirely?
    There are ways to eliminate the HTTP API but eliminating unlocking altogether is still being throught out

Current model optimizes latency and minimizing operational friction; the trade-off is a continuously available credential endpoint while unlocked.