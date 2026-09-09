"""The FunnelForge adapter. Nine modules, and the module list is the gate.

    templates.py   the approved copy, and why it is here rather than in FunnelForge
    gate.py        the two refusals the design condition requires, in the handler
    upstream.py    the four FunnelForge routes, each called and its body read
    modules.py     the dispatch map - the spelling of record for every other side
    app.py         GET /_modules and POST /{module_id}

Start with `docs/plans/funnelforge-binding-RECORD.md`. It carries what was found, what
was not bound and why, the six-step price of a seventh template, and the two states
FunnelForge is in that a status code would not have distinguished.
"""
