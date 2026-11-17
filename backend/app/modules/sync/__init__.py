"""Sync package namespace.

Keep this initializer dependency-free so utility and schema imports do not
initialize API routers or database configuration. Application startup imports
the three routers explicitly from their defining modules.
"""
