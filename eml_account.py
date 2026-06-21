"""
계정 설정 저장/로드 - SQLite + base64 간단 난독화
(keyring 없이 동작, 민감정보는 별도 암호화 권장)
"""
import sqlite3, os, base64, json
from tkinter import ttk, messagebox
import tkinter as tk

DB_PATH = os.path.join(os.path.expanduser("~"), ".eml_viewer_cache.db")

def _enc(s): return base64.b64encode(s.encode()).decode() if s else ""
def _dec(s):
    try: return base64.b64decode(s.encode()).decode() if s else ""
    except: return ""

def init_account_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS accounts (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT,
            email    TEXT,
            imap_host TEXT, imap_port INTEGER, imap_ssl INTEGER,
            smtp_host TEXT, smtp_port INTEGER, smtp_ssl INTEGER,
            username TEXT, password TEXT,
            is_default INTEGER DEFAULT 0
        )""")
        conn.commit()

def save_account(data: dict):
    with sqlite3.connect(DB_PATH) as conn:
        if data.get("id"):
            conn.execute("""UPDATE accounts SET
                name=?, email=?, imap_host=?, imap_port=?, imap_ssl=?,
                smtp_host=?, smtp_port=?, smtp_ssl=?, username=?, password=?
                WHERE id=?""", (
                data["name"], data["email"],
                data["imap_host"], data["imap_port"], int(data["imap_ssl"]),
                data["smtp_host"], data["smtp_port"], int(data["smtp_ssl"]),
                data["username"], _enc(data["password"]), data["id"]
            ))
        else:
            conn.execute("""INSERT INTO accounts
                (name,email,imap_host,imap_port,imap_ssl,smtp_host,smtp_port,smtp_ssl,username,password)
                VALUES (?,?,?,?,?,?,?,?,?,?)""", (
                data["name"], data["email"],
                data["imap_host"], data["imap_port"], int(data["imap_ssl"]),
                data["smtp_host"], data["smtp_port"], int(data["smtp_ssl"]),
                data["username"], _enc(data["password"])
            ))
        conn.commit()

def load_accounts() -> list:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT * FROM accounts").fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["password"] = _dec(d["password"])
        result.append(d)
    return result

def delete_account(account_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
        conn.commit()

init_account_db()


class AccountDialog(tk.Toplevel):
    """계정 설정 다이얼로그"""
    def __init__(self, parent, account=None, on_save=None):
        super().__init__(parent)
        self.title("계정 설정")
        self.geometry("480x520")
        self.resizable(False, False)
        self.grab_set()
        self._account = account or {}
        self._on_save = on_save
        self._build()
        if account:
            self._fill(account)

    def _build(self):
        pad = dict(padx=12, pady=4)
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=8)

        # ── 기본 정보 탭
        f1 = tk.Frame(nb)
        nb.add(f1, text="기본 정보")
        fields1 = [("표시 이름", "name"), ("이메일 주소", "email"),
                   ("아이디(username)", "username"), ("비밀번호", "password")]
        self._vars = {}
        for i, (lbl, key) in enumerate(fields1):
            tk.Label(f1, text=lbl+":", anchor="w", width=16).grid(row=i, column=0, sticky="w", **pad)
            v = tk.StringVar()
            self._vars[key] = v
            show = "*" if key == "password" else ""
            tk.Entry(f1, textvariable=v, width=28, show=show).grid(row=i, column=1, sticky="w", **pad)

        # ── IMAP 탭
        f2 = tk.Frame(nb)
        nb.add(f2, text="받기 (IMAP)")
        imap_fields = [("IMAP 서버", "imap_host"), ("포트", "imap_port")]
        for i, (lbl, key) in enumerate(imap_fields):
            tk.Label(f2, text=lbl+":", anchor="w", width=14).grid(row=i, column=0, sticky="w", **pad)
            v = tk.StringVar(value="993" if key == "imap_port" else "")
            self._vars[key] = v
            tk.Entry(f2, textvariable=v, width=28).grid(row=i, column=1, sticky="w", **pad)
        self._vars["imap_ssl"] = tk.BooleanVar(value=True)
        tk.Checkbutton(f2, text="SSL 사용 (권장)", variable=self._vars["imap_ssl"]).grid(
            row=2, column=1, sticky="w", **pad)
        # 빠른 설정
        tk.Label(f2, text="빠른 설정:", anchor="w").grid(row=3, column=0, sticky="w", **pad)
        preset_frame = tk.Frame(f2)
        preset_frame.grid(row=3, column=1, sticky="w", **pad)
        for name, host, port in [("Naver","imap.naver.com",993),
                                   ("Daum","imap.daum.net",993),
                                   ("Gmail","imap.gmail.com",993)]:
            tk.Button(preset_frame, text=name, relief="groove", padx=6,
                      command=lambda h=host, p=port: self._set_imap(h,p)).pack(side="left", padx=2)

        # ── SMTP 탭
        f3 = tk.Frame(nb)
        nb.add(f3, text="보내기 (SMTP)")
        smtp_fields = [("SMTP 서버", "smtp_host"), ("포트", "smtp_port")]
        for i, (lbl, key) in enumerate(smtp_fields):
            tk.Label(f3, text=lbl+":", anchor="w", width=14).grid(row=i, column=0, sticky="w", **pad)
            v = tk.StringVar(value="465" if key == "smtp_port" else "")
            self._vars[key] = v
            tk.Entry(f3, textvariable=v, width=28).grid(row=i, column=1, sticky="w", **pad)
        self._vars["smtp_ssl"] = tk.BooleanVar(value=True)
        tk.Checkbutton(f3, text="SSL 사용 (권장)", variable=self._vars["smtp_ssl"]).grid(
            row=2, column=1, sticky="w", **pad)
        preset_frame2 = tk.Frame(f3)
        preset_frame2.grid(row=3, column=1, sticky="w", **pad)
        tk.Label(f3, text="빠른 설정:", anchor="w").grid(row=3, column=0, sticky="w", **pad)
        for name, host, port in [("Naver","smtp.naver.com",465),
                                   ("Daum","smtp.daum.net",465),
                                   ("Gmail","smtp.gmail.com",465)]:
            tk.Button(preset_frame2, text=name, relief="groove", padx=6,
                      command=lambda h=host, p=port: self._set_smtp(h,p)).pack(side="left", padx=2)

        # 버튼
        btn_f = tk.Frame(self)
        btn_f.pack(fill="x", padx=10, pady=(0,10))
        tk.Button(btn_f, text="연결 테스트", command=self._test, relief="groove", padx=10).pack(side="left")
        tk.Button(btn_f, text="저장", command=self._save, relief="groove", padx=16).pack(side="right")
        tk.Button(btn_f, text="취소", command=self.destroy, relief="groove", padx=10).pack(side="right", padx=4)

    def _fill(self, a):
        for k, v in self._vars.items():
            val = a.get(k, "")
            if isinstance(v, tk.BooleanVar):
                v.set(bool(val))
            else:
                v.set(str(val) if val else "")

    def _set_imap(self, host, port):
        self._vars["imap_host"].set(host)
        self._vars["imap_port"].set(str(port))

    def _set_smtp(self, host, port):
        self._vars["smtp_host"].set(host)
        self._vars["smtp_port"].set(str(port))

    def _collect(self):
        return {
            "id":        self._account.get("id"),
            "name":      self._vars["name"].get().strip(),
            "email":     self._vars["email"].get().strip(),
            "username":  self._vars["username"].get().strip(),
            "password":  self._vars["password"].get(),
            "imap_host": self._vars["imap_host"].get().strip(),
            "imap_port": int(self._vars["imap_port"].get() or 993),
            "imap_ssl":  self._vars["imap_ssl"].get(),
            "smtp_host": self._vars["smtp_host"].get().strip(),
            "smtp_port": int(self._vars["smtp_port"].get() or 465),
            "smtp_ssl":  self._vars["smtp_ssl"].get(),
        }

    def _test(self):
        data = self._collect()
        import imaplib, ssl as ssl_mod
        try:
            if data["imap_ssl"]:
                conn = imaplib.IMAP4_SSL(data["imap_host"], data["imap_port"])
            else:
                conn = imaplib.IMAP4(data["imap_host"], data["imap_port"])
            conn.login(data["username"], data["password"])
            conn.logout()
            messagebox.showinfo("연결 성공", "IMAP 연결 및 로그인 성공!", parent=self)
        except Exception as ex:
            messagebox.showerror("연결 실패", str(ex), parent=self)

    def _save(self):
        data = self._collect()
        if not data["name"] or not data["email"]:
            messagebox.showwarning("입력 오류", "표시 이름과 이메일 주소는 필수입니다.", parent=self)
            return
        save_account(data)
        if self._on_save:
            self._on_save()
        messagebox.showinfo("저장 완료", "계정이 저장되었습니다.", parent=self)
        self.destroy()


class AccountManagerDialog(tk.Toplevel):
    """계정 목록 관리 다이얼로그"""
    def __init__(self, parent):
        super().__init__(parent)
        self.title("계정 관리")
        self.geometry("500x320")
        self.grab_set()
        self._parent = parent
        self._build()
        self._refresh()

    def _build(self):
        cols = ("name","email","imap_host","smtp_host")
        self._tree = ttk.Treeview(self, columns=cols, show="headings", height=8)
        for col, lbl, w in [("name","이름",100),("email","이메일",160),
                              ("imap_host","IMAP",110),("smtp_host","SMTP",110)]:
            self._tree.heading(col, text=lbl)
            self._tree.column(col, width=w, stretch=False)
        self._tree.pack(fill="both", expand=True, padx=10, pady=8)

        btn_f = tk.Frame(self)
        btn_f.pack(fill="x", padx=10, pady=(0,10))
        tk.Button(btn_f, text="추가", relief="groove", padx=10,
                  command=self._add).pack(side="left", padx=2)
        tk.Button(btn_f, text="수정", relief="groove", padx=10,
                  command=self._edit).pack(side="left", padx=2)
        tk.Button(btn_f, text="삭제", relief="groove", padx=10,
                  command=self._delete).pack(side="left", padx=2)
        tk.Button(btn_f, text="닫기", relief="groove", padx=10,
                  command=self.destroy).pack(side="right")

    def _refresh(self):
        self._accounts = load_accounts()
        self._tree.delete(*self._tree.get_children())
        for a in self._accounts:
            self._tree.insert("", "end", iid=str(a["id"]),
                              values=(a["name"], a["email"], a["imap_host"], a["smtp_host"]))

    def _selected(self):
        sel = self._tree.selection()
        if not sel:
            messagebox.showinfo("알림", "계정을 선택하세요.", parent=self)
            return None
        aid = int(sel[0])
        return next((a for a in self._accounts if a["id"] == aid), None)

    def _add(self):
        AccountDialog(self, on_save=self._refresh)

    def _edit(self):
        a = self._selected()
        if a:
            AccountDialog(self, account=a, on_save=self._refresh)

    def _delete(self):
        a = self._selected()
        if a and messagebox.askyesno("삭제 확인", f"'{a['name']}' 계정을 삭제할까요?", parent=self):
            delete_account(a["id"])
            self._refresh()
