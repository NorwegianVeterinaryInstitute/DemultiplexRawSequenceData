# Unlocking Bitwarden on seqtech00

Needed after seqtech00 reboots or when the demux script reports that Bitwarden is locked or not running. Takes about two minutes with a bit of practice.

## 1. Log in to seqtech00

1. Click the Windows **Start** button, type `PuTTY` and click **PuTTY**.
2. The **PuTTY Configuration** window opens. In the list under **Saved Sessions**, double-click `seqtech00.vetinst.no`. A black terminal window opens.
3. At `login as:` type `seqtech` and press **Enter**. The SSH key we created logs you in with no password.

## 2. Log in to Bitwarden (if needed)

Type:

    /usr/local/bin/bw login

It asks for three things, in order:

* your Bitwarden e-mail (cathrine.arnason.boe@vetinst.no)
* your master password
* the one-time code Bitwarden sends to your e-mail.

If it answers "You are already logged in", go to step 3.

## 3. Restart the Bitwarden service

Type both lines, pressing **Enter** after each:

    systemctl --user stop bw-serve.service
    systemctl --user start bw-serve.service

## 4. Unlock the vault

Type:

    /usr/local/bin/vault_unlock.sh

It asks for your master password. Nothing is shown while you type. Press **Enter** when done. No message means it worked.

## 5. Check

Type:

    /usr/local/bin/vault_status.sh

It answers in one line. "Vault is UNLOCKED. Everything is ready." means you are done. Any other answer tells you what to run and which step to go back to.

## 6. Log out

Type `exit` and press **Enter**. The window closes. The Bitwarden service keeps running after you log out.

## 7. If something goes wrong

Redo steps 3 and 4. If it still fails, send support the exact text on the screen.
