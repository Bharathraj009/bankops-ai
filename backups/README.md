# Historical verification source

This directory contains authored Java, SQL and PowerShell verification programs,
not database dumps or generated response evidence. Current automated tests and
isolated startup are in the [testing guide](../docs/TESTING.md) and
[local runbook](../local/README.md).

These programs predate current identity/database controls and are not supported
setup commands. `verify-workflow.ps1` targets port 18080, creates accounts and
development funding, and writes response artifacts. Do not run it against retained
or real banking data. SQL/Java probes may also write synthetic fixtures; review
before use in a disposable database. No private response or dump belongs in Git.
