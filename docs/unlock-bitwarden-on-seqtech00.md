# Unlocking Bitwarden on seqtech00

For Cathrine. Needed after seqtech00 reboots or when the demux script reports that Bitwarden is locked or not running. Takes about two minutes with a bit of practice

## 1. Log in to seqtech00

1. Open PuTTY.
2. Double-click the saved session `seqtech00.vetinst.no`.
3. At `login as:` type `seqtech` and press Enter. The SSH key we created will log you in with  no password.

## 2. Log in to Bitwarden (only if asked)

Type:

    /usr/local/bin/bw login

It asks for three things, in order: i
* your Bitwarden e-mail (cathrine.arnason.boe@vetinst.no)
* your master password
* and the one-time code Bitwarden sends to your e-mail.

If it answers "You are already logged in", skip to step 3.

## 3. Restart the Bitwarden service

Type both lines, pressing Enter after each:

    systemctl --user stop bw-serve.service
    systemctl --user start bw-serve.service

## 4. Unlock the vault

Type:

    /usr/local/bin/vault_unlock.sh

It asks for your master password. Nothing is shown while you type. press Enter when done. No message means it worked.

## 5. Check

Type:

    /usr/local/bin/vault_status.sh

It answers in one line. "Vault is UNLOCKED. Everything is ready" means you are done. Any other answer tells you what to run and which step to go back to.

## 6. Log out

Type `exit` and press Enter. The service keeps running after you log out.

If any step fails, send support the exact text on the screen.
