"""A small deterministic store used by the benchmark, with server-side state so success can be checked
without trusting what an agent says."""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PRODUCTS = {
    1: ("Steel Kettle", "Kitchen", "34.50", 9),
    2: ("Glass Kettle", "Kitchen", "24.99", 4),
    3: ("Copper Kettle", "Kitchen", "59.00", 2),
    4: ("Desk Lamp", "Home", "18.00", 15),
    5: ("Trowel Set", "Garden", "12.50", 12),
    6: ("Garden Hose", "Garden", "29.95", 7),
    7: ("Bamboo Tray", "Home", "15.25", 30),
    8: ("Salt Mill", "Kitchen", "21.40", 18),
}
CATEGORIES = ["Kitchen", "Home", "Garden"]
STATE = {"cart": {}, "login": False}
LOCK = threading.Lock()

# /list: 4 pages x 10 items; the target SKU is on page 3
LIST_ITEMS = [(f"ZX-{4400 + i}", f"Item {i:02d}") for i in range(1, 41)]
LIST_ITEMS[(3 - 1) * 10 + 4] = ("ZX-4471", "Brass Hinge")        # page 3, 5th row

ABOUT = ("<h1>About Demo Store</h1><p>We sell useful things for the home, kitchen and garden.</p>"
         "<p>" + "Our team cares about quality and honest service. " * 6 + "</p>"
         "<p>Demo Store was founded in 1987 in Chicago by two friends.</p>"
         "<p>" + "We ship across the country and offer easy returns. " * 6 + "</p>")


def page(title: str, body: str, banner: bool = False) -> bytes:
    nav = ('<nav><a href="/">Home</a> <a href="/about">About</a> <a href="/login">Login</a> '
           '<a href="/cart">Cart</a></nav>')
    cookie = ""
    if banner:
        cookie = ('<div id="cookie" style="position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:99;'
                  'display:flex;align-items:center;justify-content:center"><div style="background:#fff;padding:24px">'
                  '<p>We use cookies to improve your experience.</p>'
                  '<button onclick="document.cookie=\'ok=1\';document.getElementById(\'cookie\').remove()">Accept all</button> '
                  '<button onclick="document.cookie=\'ok=1\';document.getElementById(\'cookie\').remove()">Reject</button>'
                  '</div></div><script>if(document.cookie.includes("ok=1"))document.getElementById("cookie").remove()</script>')
    return (f"<!doctype html><html><head><meta charset=utf-8><title>{title}</title></head><body>{cookie}{nav}{body}</body></html>").encode()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: bytes, status: int = 200, ctype: str = "text/html; charset=utf-8") -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        u = urlparse(self.path)
        q = parse_qs(u.query)
        path = u.path
        if path == "/__state":
            with LOCK:
                return self._send(json.dumps(STATE).encode(), ctype="application/json")
        if path == "/__reset":
            with LOCK:
                STATE.update(cart={}, login=False)
            return self._send(b"ok", ctype="text/plain")
        if path == "/":
            cats = " ".join(f'<a href="/category/{c.lower()}">{c}</a>' for c in CATEGORIES)
            featured = "".join(f'<li><a href="/product/{i}">{p[0]}</a> - ${p[2]}</li>' for i, p in list(PRODUCTS.items())[:4])
            body = (f'<h1>Demo Store</h1><form action="/search"><input name="q" placeholder="Search products">'
                    f'<button type="submit">Search</button></form><h2>Categories</h2><p>{cats}</p>'
                    f'<h2>Featured</h2><ul>{featured}</ul>')
            return self._send(page("Demo Store", body, banner=True))
        if path == "/search":
            term = (q.get("q", [""])[0]).lower()
            hits = [(i, p) for i, p in PRODUCTS.items() if term and term in p[0].lower()]
            items = "".join(f'<li><a href="/product/{i}">{p[0]}</a> - ${p[2]}</li>' for i, p in hits) or "<li>No results</li>"
            return self._send(page("Search", f'<h1>Results for "{term}"</h1><form action="/search"><input name="q" '
                                              f'placeholder="Search products"><button>Search</button></form><ul>{items}</ul>'))
        if path.startswith("/category/"):
            cat = path.rsplit("/", 1)[1]
            hits = [(i, p) for i, p in PRODUCTS.items() if p[1].lower() == cat]
            items = "".join(f'<li><a href="/product/{i}">{p[0]}</a> - ${p[2]}</li>' for i, p in hits)
            return self._send(page(cat.title(), f"<h1>{cat.title()}</h1><ul>{items}</ul>"))
        if path.startswith("/product/"):
            try:
                pid = int(path.rsplit("/", 1)[1])
                name, cat, price, stock = PRODUCTS[pid]
            except (ValueError, KeyError):
                return self._send(page("Not found", "<h1>Not found</h1>"), 404)
            body = (f'<h1>{name}</h1><p>Category: {cat}</p><p>Price: ${price}</p><p>In stock: {stock}</p>'
                    f'<button id="add" onclick="fetch(\'/api/cart?id={pid}\',{{method:\'POST\'}}).then(()=>'
                    f'document.getElementById(\'msg\').textContent=\'Added to cart\')">Add to cart</button><p id="msg"></p>')
            return self._send(page(name, body))
        if path == "/cart":
            with LOCK:
                items = "".join(f"<li>{PRODUCTS[int(i)][0]} x {n}</li>" for i, n in STATE["cart"].items()) or "<li>Cart is empty</li>"
            return self._send(page("Cart", f"<h1>Your cart</h1><ul>{items}</ul>"))
        if path == "/about":
            return self._send(page("About", ABOUT))
        if path == "/login":
            body = ('<h1>Log in</h1><form method="post" action="/login"><label>Username <input name="username"></label> '
                    '<label>Password <input name="password" type="password"></label><button type="submit">Log in</button></form>')
            return self._send(page("Login", body))
        if path == "/list":
            n = max(1, min(4, int((q.get("page", ["1"])[0]) or 1)))
            rows = "".join(f"<tr><td>{s}</td><td>{nm}</td></tr>" for s, nm in LIST_ITEMS[(n - 1) * 10:n * 10])
            nav = ""
            if n > 1:
                nav += f'<a href="/list?page={n - 1}">Previous</a> '
            nav += " ".join(f'<a href="/list?page={k}">{k}</a>' for k in range(1, 5))
            if n < 4:
                nav += f' <a href="/list?page={n + 1}">Next</a>'
            return self._send(page("Parts list", f"<h1>Parts list (page {n} of 4)</h1><table><tr><th>SKU</th><th>Name</th></tr>{rows}</table><p>{nav}</p>"))
        self._send(page("Not found", "<h1>Not found</h1>"), 404)

    def do_POST(self) -> None:
        u = urlparse(self.path)
        length = int(self.headers.get("Content-Length") or 0)
        data = parse_qs(self.rfile.read(length).decode()) if length else {}
        if u.path == "/api/cart":
            pid = parse_qs(u.query).get("id", [""])[0]
            with LOCK:
                STATE["cart"][pid] = STATE["cart"].get(pid, 0) + 1
            return self._send(b"{}", ctype="application/json")
        if u.path == "/login":
            ok = data.get("username", [""])[0] == "alice" and data.get("password", [""])[0] == "pw-1234"
            if ok:
                with LOCK:
                    STATE["login"] = True
                return self._send(page("Account", "<h1>Welcome, Alice Anderson</h1><p>You are signed in.</p>"))
            return self._send(page("Login", "<h1>Log in</h1><p>Wrong username or password.</p>"), 401)
        self._send(b"{}", 404, "application/json")


def serve(port: int = 0) -> tuple[ThreadingHTTPServer, str]:
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_port}"


if __name__ == "__main__":
    s, url = serve(8765)
    print(url)
    threading.Event().wait()
