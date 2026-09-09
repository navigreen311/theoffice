"""Forge adapters authored in The Office.

An adapter normally lives inside the Forge it serves — `docs/forge-adapter.md` names
`medlink-wholesale/backend/app/api/forge.py` as the template. FunnelForge's is here
instead, and the reason is recorded rather than assumed: the FunnelForge repository is
out of scope for the package that wrote this (P-13), so the binding was authored where
it could be read and tested. See `docs/plans/funnelforge-binding-RECORD.md` for what
that costs and what has to happen before a call is made.
"""
