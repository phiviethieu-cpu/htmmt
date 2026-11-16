"""Giao thức ứng dụng FLSync chạy trên TCP.

Header cố định 20 byte, big-endian:
  magic   4B  b'FLSY'
  version 1B  1
  type    1B  HELLO=1, GLOBAL=2, UPDATE=3, ACK=4, BYE=5
  round   4B  số thứ tự vòng
  node    2B  định danh Edge Node (0 = server)
  length  8B  độ dài payload (byte)
"""
import struct

MAGIC = b"FLSY"
VERSION = 1
HDR = struct.Struct("!4sBBIHQ")
HELLO, GLOBAL, UPDATE, ACK, BYE = 1, 2, 3, 4, 5
CHUNK = 64 * 1024


def send_msg(sock, mtype, rnd, node, payload_len=0):
    """Gửi header rồi gửi payload giả (byte 0) theo từng khối 64 KB."""
    sock.sendall(HDR.pack(MAGIC, VERSION, mtype, rnd, node, payload_len))
    block = bytes(CHUNK)
    left = payload_len
    while left > 0:
        n = min(left, CHUNK)
        sock.sendall(block[:n])
        left -= n


def recv_exact(sock, n):
    buf = bytearray()
    while len(buf) < n:
        part = sock.recv(min(n - len(buf), CHUNK))
        if not part:
            raise ConnectionError("peer closed")
        buf += part
    return bytes(buf)


def recv_msg(sock):
    """Nhận một thông điệp; payload chỉ được đếm và bỏ đi, không lưu."""
    magic, ver, mtype, rnd, node, length = HDR.unpack(recv_exact(sock, HDR.size))
    if magic != MAGIC or ver != VERSION:
        raise ValueError("bad header")
    left = length
    while left > 0:
        part = sock.recv(min(left, CHUNK))
        if not part:
            raise ConnectionError("peer closed")
        left -= len(part)
    return mtype, rnd, node, length
