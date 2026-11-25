"""Giao thức ứng dụng FLSync chạy trên TCP.

Header cố định 20 byte, big-endian:
  magic   4B  b'FLSY'
  version 1B  1
  type    1B  HELLO=1, GLOBAL=2, UPDATE=3, ACK=4, BYE=5
  round   4B  số thứ tự vòng
  node    2B  định danh Edge Node (0 = server)
  length  8B  độ dài payload (byte)
Payload: trọng số mô hình đã tuần tự hoá (model.to_bytes), hoặc byte 0 giả lập
khi chỉ cần đo mạng với một kích thước cho trước.
"""
import struct

MAGIC = b"FLSY"
VERSION = 1
HDR = struct.Struct("!4sBBIHQ")
HELLO, GLOBAL, UPDATE, ACK, BYE = 1, 2, 3, 4, 5
CHUNK = 64 * 1024


def send_msg(sock, mtype, rnd, node, payload_len=0, payload=None):
    """Gửi header rồi payload theo từng khối 64 KB.

    payload=None: gửi payload_len byte 0 (chế độ đo mạng thuần).
    payload=bytes: gửi đúng dữ liệu đó (chế độ FedAvg thật).
    """
    if payload is not None:
        payload_len = len(payload)
    sock.sendall(HDR.pack(MAGIC, VERSION, mtype, rnd, node, payload_len))
    if payload is not None:
        view = memoryview(payload)
        for off in range(0, payload_len, CHUNK):
            sock.sendall(view[off:off + CHUNK])
        return
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


def recv_msg(sock, keep=False):
    """Nhận một thông điệp, trả về (type, round, node, length, data).

    keep=False: payload chỉ được đếm rồi bỏ, data = None.
    keep=True : data là toàn bộ payload (bytes) để giải tuần tự hoá.
    """
    magic, ver, mtype, rnd, node, length = HDR.unpack(recv_exact(sock, HDR.size))
    if magic != MAGIC or ver != VERSION:
        raise ValueError("bad header")
    if keep:
        return mtype, rnd, node, length, recv_exact(sock, length)
    left = length
    while left > 0:
        part = sock.recv(min(left, CHUNK))
        if not part:
            raise ConnectionError("peer closed")
        left -= len(part)
    return mtype, rnd, node, length, None
