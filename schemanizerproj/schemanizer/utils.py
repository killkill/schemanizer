"""Utility functions."""
import hashlib
import struct
import time

def fetchall(conn, query, args=None):
    """Executes query and returns all rows."""
    rows = None
    cur = conn.cursor()
    try:
        cur.execute(query, args)
        rows = cur.fetchall()
    finally:
        while cur.nextset() is not None:
            pass
        cur.close()
    return rows


def fetchone(conn, query, args=None):
    """Executes query and returns a single row."""
    row = None
    cur = conn.cursor()
    try:
        cur.execute(query, args)
        row = cur.fetchone()
    finally:
        while cur.nextset() is not None:
            pass
        cur.close()
    return row


def execute(conn, query, args=None):
    """Executes query only."""
    cur = conn.cursor()
    try:
        cur.execute(query, args)
    finally:
        while cur.nextset() is not None:
            pass
        cur.close()


def generate_request_id(request):
    """Create a unique ID for the request."""

    s = hashlib.sha1()
    s.update(str(time.time()))
    s.update(request.META['REMOTE_ADDR'])
    s.update(request.META['SERVER_NAME'])
    s.update(request.get_full_path())
    h = s.hexdigest()
    #l = long(h, 16)

    # shorten ID
    #tag = struct.pack('d', l).encode('base64').replace('\n', '').strip('=')
    return h