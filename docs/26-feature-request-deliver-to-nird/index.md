# Branch Documentation

## `26-feature-request-deliver-to-nird`

---

# Purpose

Add deterministic per-Sample_Project tar file delivery to NIRD with strict SSH validation and transfer verification.

This branch does not modify demultiplexing or QC mechanics. It modifies packaging metadata (tar upload location) and introduces structured upload logic.

---

# What Changed vs `main`

## 1. Explicit Upload Metadata

The metadata for the generated tar now carries:

* `nird_upload_location`
* `upload_to_nird` flag

Upload routing is no longer global. It is resolved per Sample_Project and stored on tar metadata (future: SQL database)

QC data is no longer uploaded?

---

## 2. NIRD_Location Invariant

All samples in a Sample_Project must resolve to exactly one identical `NIRD_Location`.

If mismatch is detected, execution aborts before packaging.

---

## 3. Deterministic Upload Routing

Upload destination is derived during packaging and becomes immutable for that tar.

All upload logic reads destination from tar metadata (SampleSheet.csv) only.

No implicit path resolution: The upload root is taken exclusively from the SampleSheet, and the final destination is deterministically constructed as SampleSheet-defined root + RunID; no environment or fallback defaults participate.

Future expansion: upload path taken from shinylims app by @magnulei via API call

---

## 4. SSH Transport Refactor

Delivery uses explicit Paramiko transport construction:

* A valid ~/.ssh/config is required; the upload host and ProxyJump chain are resolved exclusively from it and the transport cannot be constructed without it.
* ProxyJump chain resolved from `~/.ssh/config`
* One Transport per hop
* `direct-tcpip` channel wrapping
* LIFO teardown

No implicit SSH behavior.

---

## 5. Strict Host Key Enforcement

* Unknown host keys rejected
* Mismatched keys abort immediately
* No AutoAddPolicy or silent trust-on-first-use

This environment is known infrastructure. Host keys are expected to be stable. Any change indicates reinstallation key rotation, or compromise and must be investigated and resolved by the sysadmin before transfers resume.

New host keys are never learned automatically; they must be verified and added manually to the known_hosts store.

---

## 6. Authentication Model

Supports:

* SSH key authentication
* ssh-agent usage
* Bitwarden local API for password retrieval
* TOTP when required by NIRD
* Single try mechnanism: This is supposed to be a known hosts, so deviations from what we already know should be treated with suspicion.
* One authentication mechanism per hop
    * in order of detection: ssh agent, ssh key, 2FA, keyboard-interactive
    * there is a bit of cheating going on with `login.posit.vetinst.no`, but that will be eliminated in the future once I figure a better way to detect the authentication mechanisms.

No credentials are written to disk, but BitWarden service leaves an open vector. See `risk_matrix.md` for more details and mitigation mechanisms.

---

### Bitwarden Service Requirements

Uploads depend on a user-scoped Bitwarden HTTP API service. License will be aquired from the IT department via a service account user to minimize the attack vector on passwords. Service account will be assigned to the person heading the sequencing. Due to the fact that the account logging in to NIRD has 2FA and that 2FA is per-person, a 'second person as backup' was not under design configuration and not under current consideration (we would have to deal with user managment)

#### 1. Bitwarden CLI Initialization (one-time setup)

The uploading user must initialize Bitwarden via:

```
/usr/local/bin/bw login
```

Follow the CLI instructions to complete login and device registration. 

Note: the BitWarden password cannot be the same as the domain password of the user

---

#### 2. Install `bw-serve.service`

The provided `bw-serve.service` must be installed in the user systemd directory:

```
~/.config/systemd/user/bw-serve.service
```

    [Unit]
    Description=Bitwarden CLI serve (loopback only)
    Documentation=[https://bitwarden.com/blog/bringing-restful-api-to-the-bitwarden-cli/](https://bitwarden.com/blog/bringing-restful-api-to-the-bitwarden-cli/) [https://bitwarden.com/help/vault-management-api/](https://bitwarden.com/help/vault-management-api/)
    
    [Service]
    ExecStart=/usr/local/bin/bw serve --hostname 127.0.0.1 --port 8087
    ExecStartPost=/usr/bin/sh -c 'if [ "$(cut -d. -f1 /proc/uptime)" -lt 120 ]; then printf "Vault locked due to reboot. Run /usr/local/bin/vault_unlock.sh\n" | /usr/bin/mailx -s "Bitwarden vault locked due to seqtech reboot" george.marselis@vetinst.no; fi'
    Restart=no
    StartLimitAction=none
    PrivateTmp=yes
    NoNewPrivileges=yes
    ProtectSystem=strict
    ProtectHome=read-only
    ReadWritePaths="/data/.config/Bitwarden CLI"
    RestrictAddressFamilies=AF_INET AF_UNIX

    [Install]
    WantedBy=default.target

Then enable and start it:

```
systemctl --user daemon-reload
systemctl --user enable bw-serve.service
systemctl --user start bw-serve.service
```

This exposes the local Bitwarden API endpoint required by the upload logic.

`bw-serve.service` must be running for uploads to function.

---

#### 3. Vault Unlock Requirement

Before uploads can proceed, the vault must be unlocked manually:

```
/usr/local/bin/vault_unlock.sh
```

The user will be prompted to enter their Bitwarden master password. As mentioned the Bitwarden password should not be the same as the VI password.

The vault remains unlocked in memory for the active session.

Uploads will fail if:

* `bw-serve.service` is not running
* The vault is locked
* The CLI is not logged in

---

## 7. Transfer Verification

After upload:

* Precomputed local checksum is read in and compared against the remote recalculated checksum.

Success requires checksum match.

---

# New Failure Classes Introduced

* Channel open failure
* EOF during transfer
* Remote quota or disk full
* Checksum mismatch
* Host key mismatch

All logged with:

* RunID
* Sample_Project
* Remote path

---

# Configuration Changes

Requires:

* Valid `~/.ssh/config` with correct ProxyJump definitions
* Known host entries present (pre-resolved via connecting to each host)
* Bitwarden local API running if password-based/2FA auth is used

No new global config keys introduced beyond upload metadata.

---

# Operational Impact

* Upload failures now abort explicitly.
* Misrouted projects fail early.
* Host key changes require operator intervention.

Demultiplex and QC remain unaffected.

---

# Compatibility

* Backward compatible with existing run processing, up to `251110_M09180_0048_000000000-M7V7K`: previous runs will need their sample sheet regenerated from shinylims
* Does not alter existing tar structure.
* Only affects delivery stage.

---

# Rollback

Rollback removes deterministic routing and reverts to previous upload logic.

No data format migration required.

---


