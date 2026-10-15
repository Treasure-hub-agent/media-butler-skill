"""纯标准库 bencode 解码器，用于读取 torrent metadata 的文件列表。"""

def decode(data: bytes):
    value, pos = _parse(data, 0)
    return value

def _parse(data: bytes, i: int):
    c = data[i:i + 1]
    if c == b"i":
        j = data.index(b"e", i)
        return int(data[i + 1:j]), j + 1
    if c == b"l":
        i += 1
        out = []
        while data[i:i + 1] != b"e":
            v, i = _parse(data, i)
            out.append(v)
        return out, i + 1
    if c == b"d":
        i += 1
        out = {}
        while data[i:i + 1] != b"e":
            k, i = _parse(data, i)
            v, i = _parse(data, i)
            out[k] = v
        return out, i + 1
    j = data.index(b":", i)
    n = int(data[i:j])
    j += 1
    return data[j:j + n], j + n

def list_files(info: dict) -> list:
    """把 info 字典转成 [{index, path, length}]；index 为 1 基（对应 aria2 --select-file）。

    path 为 torrent 内的相对路径（多文件时相对根目录 name），单文件时即 name 本身。
    """
    name = _text(info.get(b"name", b""))
    if b"files" not in info:
        return [{"index": 1, "path": name, "length": int(info.get(b"length", 0))}]
    out = []
    for n, f in enumerate(info[b"files"], 1):
        parts = [_text(p) for p in f.get(b"path", [])]
        out.append({
            "index": n,
            "path": "/".join(parts),
            "length": int(f.get(b"length", 0)),
        })
    return out

def _text(b) -> str:
    if isinstance(b, bytes):
        return b.decode("utf-8", "replace")
    return str(b)

def decode_torrent_file(path: str) -> dict:
    with open(path, "rb") as f:
        return decode(f.read())
