#!/usr/bin/env python3
"""Mô hình học máy cục bộ cho FL: mạng nơ-ron MLP 64-512-512-10 viết bằng numpy.

  - Dữ liệu: bài toán phân loại 10 lớp, 64 đặc trưng, sinh tổng hợp với seed cố định
    (mọi Edge Node và Aggregator sinh ra cùng một tập, mỗi node chỉ dùng phần của mình).
  - Hàm mất mát: cross-entropy trên softmax.
  - Tối ưu: SGD mini-batch.
  - Tuần tự hoá: toàn bộ trọng số nối thành một mảng float32 big-endian (~1,2 MB),
    đây chính là payload của thông điệp GLOBAL/UPDATE trong FLSync.

Chạy thử không cần mạng:  python3 model.py   (FedAvg cục bộ, in độ chính xác từng vòng)
"""
import numpy as np

LAYERS = [64, 512, 512, 10]
N_TRAIN, N_TEST = 6000, 2000
SEED = 2026
LR, BATCH, EPOCHS = 0.02, 32, 1


# ---------- Dữ liệu ----------
def make_dataset(seed=SEED):
    """10 lớp, mỗi lớp là 3 cụm Gauss trong không gian 64 chiều, có chồng lấn."""
    rng = np.random.default_rng(seed)
    centers = rng.normal(0, 1.0, size=(10, 3, LAYERS[0]))
    n = N_TRAIN + N_TEST
    y = rng.integers(0, 10, size=n)
    sub = rng.integers(0, 3, size=n)
    x = centers[y, sub] + rng.normal(0, 1.6, size=(n, LAYERS[0]))
    x = x.astype(np.float32)
    return (x[:N_TRAIN], y[:N_TRAIN]), (x[N_TRAIN:], y[N_TRAIN:])


def partition(x, y, n_clients, node_id):
    """Chia đều tập huấn luyện cho n_clients node (IID); node_id đánh số từ 1."""
    idx = np.array_split(np.arange(len(x)), n_clients)[node_id - 1]
    return x[idx], y[idx]


# ---------- Mạng nơ-ron ----------
def init_params(seed=SEED):
    rng = np.random.default_rng(seed + 1)
    params = []
    for fan_in, fan_out in zip(LAYERS[:-1], LAYERS[1:]):
        w = rng.normal(0, np.sqrt(2.0 / fan_in), size=(fan_in, fan_out)).astype(np.float32)
        params += [w, np.zeros(fan_out, dtype=np.float32)]
    return params


def forward(params, x):
    acts = [x]
    h = x
    for i in range(0, len(params), 2):
        h = h @ params[i] + params[i + 1]
        if i < len(params) - 2:
            h = np.maximum(h, 0)            # ReLU
        acts.append(h)
    return acts


def softmax_ce(logits, y):
    z = logits - logits.max(axis=1, keepdims=True)
    p = np.exp(z)
    p /= p.sum(axis=1, keepdims=True)
    loss = -np.log(p[np.arange(len(y)), y] + 1e-12).mean()
    return loss, p


def sgd_train(params, x, y, epochs=EPOCHS, lr=LR, batch=BATCH, seed=0):
    """Huấn luyện cục bộ: SGD mini-batch, lan truyền ngược thủ công."""
    params = [p.copy() for p in params]
    rng = np.random.default_rng(seed)
    for _ in range(epochs):
        order = rng.permutation(len(x))
        for s in range(0, len(x), batch):
            b = order[s:s + batch]
            acts = forward(params, x[b])
            _, p = softmax_ce(acts[-1], y[b])
            g = p
            g[np.arange(len(b)), y[b]] -= 1
            g /= len(b)
            for i in range(len(params) - 2, -1, -2):
                a_in = acts[i // 2]
                gw, gb = a_in.T @ g, g.sum(axis=0)
                if i > 0:
                    g = (g @ params[i].T) * (a_in > 0)
                params[i] -= lr * gw
                params[i + 1] -= lr * gb
    return params


def evaluate(params, x, y):
    logits = forward(params, x)[-1]
    loss, p = softmax_ce(logits, y)
    return float((p.argmax(axis=1) == y).mean()), float(loss)


# ---------- FedAvg và tuần tự hoá ----------
def fedavg(updates):
    """updates: danh sách (params, số mẫu). Trung bình có trọng số theo số mẫu."""
    total = sum(n for _, n in updates)
    return [sum(p[i] * (n / total) for p, n in updates).astype(np.float32)
            for i in range(len(updates[0][0]))]


def to_bytes(params):
    return b"".join(p.astype(">f4").tobytes() for p in params)


def from_bytes(buf):
    flat = np.frombuffer(buf, dtype=">f4").astype(np.float32)
    params, off = [], 0
    for fan_in, fan_out in zip(LAYERS[:-1], LAYERS[1:]):
        for shape in ((fan_in, fan_out), (fan_out,)):
            k = int(np.prod(shape))
            params.append(flat[off:off + k].reshape(shape).copy())
            off += k
    return params


def model_bytes():
    return sum((a + 1) * b for a, b in zip(LAYERS[:-1], LAYERS[1:])) * 4


if __name__ == "__main__":
    import time
    (xtr, ytr), (xte, yte) = make_dataset()
    g = init_params()
    print(f"model size = {model_bytes()} byte, acc0 = {evaluate(g, xte, yte)[0]:.3f}")
    n = 4
    for r in range(1, 31):
        t = time.perf_counter()
        ups = []
        for k in range(1, n + 1):
            xs, ys = partition(xtr, ytr, n, k)
            ups.append((sgd_train(from_bytes(to_bytes(g)), xs, ys, seed=r * 100 + k), len(xs)))
        g = fedavg(ups)
        acc, loss = evaluate(g, xte, yte)
        print(f"round {r:2d}: acc={acc:.3f} loss={loss:.3f}  ({(time.perf_counter() - t) / n:.2f} s/client)")
