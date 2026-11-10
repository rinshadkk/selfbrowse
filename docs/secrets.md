# Passwords and secrets

Never put a password in the task text. The task goes to the model; a secret should not. Give the secret to Selfbrowse instead, under a name. The model is told only the name (`<secret:NAME>`), writes that placeholder when it types, and Selfbrowse swaps in the real value at the keyboard. The value never appears in the prompt, the page list, the result, the step history or traces.

**Command line.** A full example, logging in to a site and reading something behind the login:

```bash
# 1. Put the secrets in your shell. `read -s` keeps the password out of your history.
export SELFBROWSE_SECRET_user='me@example.com'
read -s "SELFBROWSE_SECRET_pw?Password: " && export SELFBROWSE_SECRET_pw     # zsh
# bash:  read -s -p "Password: " SELFBROWSE_SECRET_pw && export SELFBROWSE_SECRET_pw

# 2. Run the task. Say which site to use, and lock the run to it.
selfbrowse --headed --allow-domain example.com \
  "Go to example.com/login, sign in with <secret:user> and <secret:pw>, then tell me my latest order number"
```

The name after `SELFBROWSE_SECRET_` is the name the model uses: `SELFBROWSE_SECRET_pw` becomes `<secret:pw>`. Every `SELFBROWSE_SECRET_*` variable is made available, and the model is told the names even if your task does not mention them.

For one command only, set the variable in front of it (the value is still visible in your history, so use this for throwaway values):

```bash
SELFBROWSE_SECRET_pw='throwaway' selfbrowse "log in to the staging site and open settings"
```

Or keep them in a file outside the project and load it when you need it:

```bash
# ~/.selfbrowse-secrets  (chmod 600; never commit it)
export SELFBROWSE_SECRET_user='me@example.com'
export SELFBROWSE_SECRET_pw='your-password'
```
```bash
source ~/.selfbrowse-secrets && selfbrowse "sign in to example.com and open my orders"
```

To be asked for a value each time, so it is never stored in your environment, name it with `--secret`:

```bash
selfbrowse --secret pw "Sign in to example.com as me@example.com with <secret:pw> and tell me my latest order number"
# Value for secret 'pw' (not shown):
```

Selfbrowse has no `--secret NAME=value` form on purpose: a value on the command line shows up in `ps` and your history.

**Python.**

```python
import os
BrowseAgent("log in and open my orders", sensitive={"user": "me@example.com", "pw": os.environ["SITE_PW"]})
```

**MCP server.** Set the same `SELFBROWSE_SECRET_<name>` variables in the server's environment (the `env` block of your client config). With `browser_type`, the calling assistant passes `<secret:pw>` as the text.

Tips:

- Name the field in your task ("log in with <secret:user> and <secret:pw>") if the site has more than one form.
- Use `--profile DIR` to log in once and keep the session, so later runs need no secret.
- For 2FA codes, CAPTCHAs and one-off values you do not want stored, let the model call `ask_human`; you type it in the browser window.
- Secrets hide what the model sees from the agent's side. They do not stop a page from showing your own details back (an account name, an email address). Add `--redact-pii` (or `--redact-presidio` for names too) for that.
- Pair secrets with `--allow-domain`, so a credential can only be typed on the site you meant.
