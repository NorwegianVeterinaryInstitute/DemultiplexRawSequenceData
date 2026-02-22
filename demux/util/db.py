import peewee

"""
SQLite persistence layer for demultiplex runs using Peewee ORM.

Owns DB connection lifecycle, schema initialization, and atomic writes for runs,
phases, barcodes, and prepared files. No workflow logic; steps call this module
to record state, timing, artifacts, and outcomes.
"""
