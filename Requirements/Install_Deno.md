### Run these commands in sequence in terminal

`mkdir -p ~/.local/opt/deno`
`DENO_INSTALL="$HOME/.local/opt/deno" \ curl -fsSL https://deno.land/install.sh | sh`
`source ~/.bashrc`
`echo $SHELL` (should show `echo $SHELL`)
`deno --version` (should show version)