"""
EML 이메일 뷰어
Copyright (c) 2025 Axiosoft. All rights reserved.

- 오류 나도 꺼지지 않음 (전역 예외 처리)
- 헤더만 빠르게 로딩, 본문은 클릭 시 파싱 (지연 로딩)
- Treeview iid = 숫자 (한글 경로 버그 해결)
- 200개씩 중간 목록 표시
"""
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import email, email.header, email.policy, email.utils
import os, sys, tempfile, webbrowser, datetime, threading, traceback, json
from pathlib import Path

# DB 캐시
try:
    from eml_db import save_emails, load_all, get_existing_basenames, delete_paths, clear_all as db_clear_all
    HAS_DB = True
except Exception:
    HAS_DB = False

# HTML 뷰어
try:
    from eml_html_viewer import HtmlPanel, HAS_WEBVIEW
except Exception:
    HAS_WEBVIEW = False
    HtmlPanel = None

# 계정 / 작성 / IMAP
try:
    from eml_account import AccountManagerDialog, load_accounts
    from eml_compose import ComposeWindow
    from eml_imap import fetch_imap
    HAS_MAIL = True
except Exception:
    HAS_MAIL = False


# ── 파싱 헬퍼 ────────────────────────────────────────────

def decode_hdr(val):
    if not val:
        return ""
    try:
        parts = email.header.decode_header(str(val))
    except Exception:
        return str(val)
    out = []
    for part, charset in parts:
        if isinstance(part, bytes):
            for enc in [charset, "utf-8", "cp949", "euc-kr", "latin-1"]:
                try:
                    out.append(part.decode(enc or "utf-8", errors="replace"))
                    break
                except Exception:
                    pass
        else:
            out.append(str(part))
    return "".join(out).strip()


def parse_header_only(path):
    """헤더만 읽어 빠르게 반환. 본문/첨부는 None."""
    with open(path, "rb") as f:
        raw = f.read()
    msg = email.message_from_bytes(raw, policy=email.policy.compat32)
    subject  = decode_hdr(msg.get("Subject", "")) or os.path.basename(path)
    from_    = decode_hdr(msg.get("From", ""))
    to_      = decode_hdr(msg.get("To", ""))
    cc_      = decode_hdr(msg.get("Cc", ""))
    date_str = msg.get("Date", "")
    try:
        date_obj = email.utils.parsedate_to_datetime(date_str)
    except Exception:
        date_obj = None
    return dict(
        path=path, subject=subject, from_=from_, to=to_, cc=cc_,
        date=date_obj, date_str=date_str,
        body_text=None, body_html=None, attachments=None,
        _raw=raw,
    )


def parse_body(e):
    """클릭 시 본문·첨부 파싱 (지연). DB 로드 시 _raw=None이면 파일에서 읽음."""
    if e["body_text"] is not None:
        return
    try:
        raw = e.get("_raw")
        if raw is None:
            with open(e["path"], "rb") as f:
                raw = f.read()
            e["_raw"] = raw
        msg = email.message_from_bytes(raw, policy=email.policy.compat32)
        body_text, body_html, attachments = "", "", []
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            fn = decode_hdr(part.get_filename() or "")
            is_attach = ("attachment" in cd or
                         ("inline" not in cd and fn and ct not in ("text/plain","text/html")))
            if is_attach and fn:
                data = part.get_payload(decode=True)
                if data:
                    attachments.append((fn, ct, data))
                continue
            if ct == "text/plain" and not body_text:
                data = part.get_payload(decode=True)
                if data:
                    cs = part.get_content_charset() or "utf-8"
                    decoded = data.decode(cs, errors="replace")
                    # null byte 제거, 줄바꿈 정규화
                    decoded = decoded.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
                    body_text = decoded
            elif ct == "text/html" and not body_html:
                data = part.get_payload(decode=True)
                if data:
                    cs = part.get_content_charset() or "utf-8"
                    body_html = data.decode(cs, errors="replace")
        e["body_text"]   = body_text
        e["body_html"]   = body_html
        e["attachments"] = attachments
    except Exception:
        e["body_text"]   = f"[본문 파싱 오류]\n{traceback.format_exc()}"
        e["body_html"]   = ""
        e["attachments"] = []


# ── 앱 ───────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("EML 이메일 뷰어  |  © 2025 Axiosoft")
        self.geometry("1150x720")
        self.minsize(800, 500)
        self.report_callback_exception = self._on_exception

        self._emails   = []
        self._filtered = []
        self._idx_map  = {}   # iid(숫자문자열) -> dict
        self._current  = None
        self._sort_col = "date"
        self._sort_rev = True
        self._loading  = False

        # DB 캐시 사용

        self._build_menu()
        self._build_ui()
        self._apply_style()
        # UI 완전히 뜬 뒤 100ms 후 복원 (mainloop 시작 후 실행 보장)
        self.after(100, self._load_config)

    # ── 전역 예외 처리 ─────────────────────────────────────
    def _on_exception(self, exc_type, exc_val, exc_tb):
        msg = "".join(traceback.format_exception(exc_type, exc_val, exc_tb))
        messagebox.showerror("오류 발생 (프로그램은 계속 실행됩니다)", msg[:1200])

    # ── 메뉴 ──────────────────────────────────────────────
    def _build_menu(self):
        mb = tk.Menu(self)
        self.config(menu=mb)
        fm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="파일", menu=fm)
        fm.add_command(label="EML 파일 열기…  Ctrl+O", command=self.open_files)
        fm.add_command(label="폴더 열기…  Ctrl+Shift+O", command=self.open_folder)
        fm.add_separator()
        fm.add_command(label="목록 비우기", command=self.clear_all)
        fm.add_separator()
        fm.add_command(label="종료", command=self.quit)
        vm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="보기", menu=vm)
        vm.add_command(label="인쇄…  Ctrl+P", command=self.print_email)
        # 계정 / 메일 메뉴
        if HAS_MAIL:
            am = tk.Menu(mb, tearoff=0)
            mb.add_cascade(label="계정", menu=am)
            am.add_command(label="계정 관리…", command=self._manage_accounts)
            am.add_separator()
            am.add_command(label="메일 받아오기 (IMAP)…", command=self._fetch_imap)
            cm = tk.Menu(mb, tearoff=0)
            mb.add_cascade(label="작성", menu=cm)
            cm.add_command(label="새 메일 작성…  Ctrl+N", command=self._compose_new)
            cm.add_command(label="답장…", command=self._compose_reply)

        hm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="도움말", menu=hm)
        hm.add_command(label="Axiosoft EML 뷰어 정보", command=self._show_about)

        self.bind_all("<Control-o>", lambda e: self.open_files())
        self.bind_all("<Control-O>", lambda e: self.open_folder())
        self.bind_all("<Control-p>", lambda e: self.print_email())
        self.bind_all("<Control-n>", lambda e: self._compose_new())

    # ── UI ────────────────────────────────────────────────
    def _build_ui(self):
        tb = tk.Frame(self, pady=5, padx=6, bg="#f0f0f0")
        tb.pack(fill="x")
        extra_btns = [("📥 받아오기", self._fetch_imap), ("✉ 새 메일", self._compose_new)] if HAS_MAIL else []
        for txt, cmd in [("📂 파일 열기", self.open_files),
                         ("🗂 폴더 열기", self.open_folder),
                         ("🖨 인쇄", self.print_email)] + extra_btns:
            tk.Button(tb, text=txt, command=cmd, relief="groove",
                      padx=8, bg="#f0f0f0").pack(side="left", padx=2)

        tk.Label(tb, text="검색:", bg="#f0f0f0").pack(side="left", padx=(14,2))
        self._sv = tk.StringVar()
        self._sv.trace_add("write", lambda *_: self._filter())
        tk.Entry(tb, textvariable=self._sv, width=22).pack(side="left")

        tk.Label(tb, text="대상:", bg="#f0f0f0").pack(side="left", padx=(8,2))
        self._fv = tk.StringVar(value="전체")
        cb = ttk.Combobox(tb, textvariable=self._fv,
                          values=["전체","제목","보낸 이","받는 이","본문"],
                          width=7, state="readonly")
        cb.pack(side="left")
        cb.bind("<<ComboboxSelected>>", lambda e: self._filter())

        tk.Label(tb, text="정렬:", bg="#f0f0f0").pack(side="left", padx=(12,2))
        self._sortv = tk.StringVar(value="날짜")
        sc = ttk.Combobox(tb, textvariable=self._sortv,
                          values=["날짜","제목","보낸 이"], width=6, state="readonly")
        sc.pack(side="left")
        sc.bind("<<ComboboxSelected>>", lambda e: self._do_sort())

        self._dirbtn = tk.Button(tb, text="↓", width=2, relief="groove",
                                  bg="#f0f0f0", command=self._toggle_dir)
        self._dirbtn.pack(side="left", padx=2)

        self._status = tk.Label(tb, text="", bg="#f0f0f0", fg="#555")
        self._status.pack(side="right", padx=10)

        self._pb = ttk.Progressbar(self, mode="indeterminate")

        pw = tk.PanedWindow(self, orient="horizontal", sashwidth=5, sashrelief="flat")
        pw.pack(fill="both", expand=True)

        # 왼쪽 목록
        lf = tk.Frame(pw, width=360)
        pw.add(lf, minsize=220)
        cols = ("subject","from","date")
        self._tree = ttk.Treeview(lf, columns=cols, show="headings", selectmode="browse")
        self._tree.heading("subject", text="제목",    command=lambda: self._col_sort("subject"))
        self._tree.heading("from",    text="보낸 이", command=lambda: self._col_sort("from_"))
        self._tree.heading("date",    text="날짜",    command=lambda: self._col_sort("date"))
        self._tree.column("subject", width=190, stretch=True)
        self._tree.column("from",    width=120, stretch=True)
        self._tree.column("date",    width=72,  stretch=False)
        vsb = ttk.Scrollbar(lf, orient="vertical", command=self._tree.yview)
        self._tree.configure(yscrollcommand=vsb.set)
        self._tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")
        self._tree.bind("<<TreeviewSelect>>", self._on_select)

        # 오른쪽 상세
        rf = tk.Frame(pw)
        pw.add(rf, minsize=420)

        hf = tk.LabelFrame(rf, text="이메일 정보", padx=8, pady=6)
        hf.pack(fill="x", padx=6, pady=(6,0))
        self._hvars = {}
        for r, (lbl, key) in enumerate([
            ("제목","subject"),("보낸 이","from_"),("받는 이","to"),
            ("참조","cc"),("날짜","date_str")
        ]):
            tk.Label(hf, text=lbl+":", anchor="w", width=7,
                     fg="#555").grid(row=r, column=0, sticky="w")
            v = tk.StringVar()
            self._hvars[key] = v
            tk.Label(hf, textvariable=v, anchor="w",
                     wraplength=580, justify="left").grid(row=r, column=1, sticky="w", padx=4)

        # 오른쪽 하단: 첨부파일 + 탭을 하나의 프레임에 고정 순서로 배치
        bottom = tk.Frame(rf)
        bottom.pack(fill="both", expand=True)

        # 답장 버튼
        if HAS_MAIL:
            reply_f = tk.Frame(bottom)
            reply_f.pack(fill="x", padx=6, pady=(4,0))
            tk.Button(reply_f, text="↩ 답장", relief="groove", padx=10,
                      command=self._compose_reply).pack(side="left")

        self._af = tk.LabelFrame(bottom, text="첨부파일", padx=8, pady=4)
        # _af는 필요할 때 bottom 안에 pack됨

        nb = ttk.Notebook(bottom)
        nb.pack(fill="both", expand=True, padx=6, pady=6)
        self._nb = nb

        tf2 = tk.Frame(nb)
        nb.add(tf2, text="텍스트")
        self._body = tk.Text(tf2, wrap="word", font=("Malgun Gothic",10),
                              relief="flat", padx=8, pady=8, state="disabled")
        vs2 = ttk.Scrollbar(tf2, command=self._body.yview)
        self._body.configure(yscrollcommand=vs2.set)
        self._body.pack(side="left", fill="both", expand=True)
        vs2.pack(side="right", fill="y")

        hf2 = tk.Frame(nb)
        nb.add(hf2, text="HTML")
        self._html = None
        self._html_panel = HtmlPanel() if HAS_WEBVIEW else None

        mode_txt = "앱 내 뷰어로 HTML을 봅니다." if HAS_WEBVIEW else "HTML 이메일은 기본 브라우저로 열립니다."
        tk.Label(hf2, text=mode_txt, pady=16, fg="#666",
                 font=("Malgun Gothic", 10)).pack()
        btn_txt = "🖥 HTML 뷰어로 보기" if HAS_WEBVIEW else "🌐 브라우저로 HTML 보기"
        self._html_btn = tk.Button(hf2, text=btn_txt,
                  command=self._open_html, padx=16, pady=6,
                  font=("Malgun Gothic", 10), relief="groove")
        self._html_btn.pack(pady=4)
        self._html_no_content = tk.Label(hf2, text="(이 이메일에는 HTML 본문이 없습니다)",
                                          fg="#aaa", font=("Malgun Gothic", 9))

    def _apply_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Treeview", rowheight=24, font=("Malgun Gothic",9))
        s.configure("Treeview.Heading", font=("Malgun Gothic",9,"bold"))
        s.map("Treeview", background=[("selected","#c5dbf5")])

    # ── 파일 열기 ──────────────────────────────────────────
    def open_files(self):
        paths = filedialog.askopenfilenames(
            title="EML 파일 선택",
            filetypes=[("이메일 파일","*.eml"),("모든 파일","*.*")])
        if paths:
            self._load_in_thread(list(paths))

    def open_folder(self):
        folder = filedialog.askdirectory(title="EML 파일이 있는 폴더 선택")
        if folder:
            paths = [str(p) for p in Path(folder).rglob("*.eml")]
            if not paths:
                messagebox.showinfo("알림", "폴더에 .eml 파일이 없습니다.")
                return
            self._load_in_thread(paths)

    def _load_in_thread(self, paths):
        if self._loading:
            messagebox.showinfo("알림", "이미 로딩 중입니다.")
            return
        # DB에 이미 있는 파일명이면 스킵
        if HAS_DB:
            existing_names = get_existing_basenames()
        else:
            existing_names = {os.path.basename(e["path"]) for e in self._emails}
        new_paths = [p for p in paths if os.path.basename(p) not in existing_names]
        if not new_paths:
            messagebox.showinfo("알림", "새로운 파일이 없습니다.")
            return

        self._loading = True
        self._pb.pack(fill="x", padx=6, pady=2)
        self._pb.start(10)
        total = len(new_paths)
        self._status.config(text=f"로딩 중… 0 / {total}")

        def worker():
            batch = []
            done  = 0
            for p in new_paths:
                try:
                    batch.append(parse_header_only(p))
                except Exception:
                    pass
                done += 1
                if len(batch) >= 200:
                    b = batch[:]
                    batch = []
                    self.after(0, lambda b=b, d=done: self._partial(b, d, total))
            self.after(0, lambda b=batch: self._done(b, total))

        threading.Thread(target=worker, daemon=True).start()

    def _partial(self, batch, done, total):
        self._emails.extend(batch)
        self._status.config(text=f"로딩 중… {done} / {total}")
        self._filter()
        if HAS_DB:
            threading.Thread(target=lambda b=batch: save_emails(b), daemon=True).start()

    def _done(self, remaining, total):
        self._emails.extend(remaining)
        self._loading = False
        self._pb.stop()
        self._pb.pack_forget()
        self._filter()
        self._status.config(text=f"총 {len(self._emails)}개 로드 완료")
        if HAS_DB:
            threading.Thread(target=lambda r=remaining: save_emails(r), daemon=True).start()

    def _save_config(self):
        pass  # DB로 대체됨

    def _load_config(self):
        """DB에서 즉시 로드 (파일 읽기 없음 → 빠름)"""
        if not HAS_DB:
            return
        try:
            self._status.config(text="DB에서 복원 중…")
            def worker():
                emails = load_all()
                self.after(0, lambda: self._on_db_load(emails))
            threading.Thread(target=worker, daemon=True).start()
        except Exception:
            pass

    def _on_db_load(self, emails):
        """DB 로드 완료 후 UI 반영"""
        if not emails:
            self._status.config(text="")
            return
        self._emails = emails
        self._filter()
        self._status.config(text=f"총 {len(emails)}개 복원 완료")

    def clear_all(self):
        self._emails.clear()
        self._filtered.clear()
        self._idx_map.clear()
        self._current = None
        self._tree.delete(*self._tree.get_children())
        self._clear_detail()
        self._status.config(text="")
        if HAS_DB:
            db_clear_all()

    # ── 정렬 / 필터 ────────────────────────────────────────
    def _filter(self):
        q     = self._sv.get().strip().lower()
        field = self._fv.get()
        if not q:
            self._filtered = list(self._emails)
        else:
            out = []
            for e in self._emails:
                targets = []
                if field in ("전체","제목"):    targets.append(e["subject"])
                if field in ("전체","보낸 이"): targets.append(e["from_"])
                if field in ("전체","받는 이"): targets.append(e["to"])
                if field in ("전체","본문"):
                    # 본문 검색은 아직 파싱 안 된 경우 스킵
                    if e["body_text"]:
                        targets.append(e["body_text"][:3000])
                if any(q in t.lower() for t in targets):
                    out.append(e)
            self._filtered = out
        self._render_tree()

    def _do_sort(self):
        m = {"날짜":"date","제목":"subject","보낸 이":"from_"}
        self._sort_col = m.get(self._sortv.get(), "date")
        self._filter()

    def _toggle_dir(self):
        self._sort_rev = not self._sort_rev
        self._dirbtn.config(text="↓" if self._sort_rev else "↑")
        self._filter()

    def _col_sort(self, col):
        self._sort_rev = not self._sort_rev if self._sort_col == col else True
        self._sort_col = col
        m = {"date":"날짜","subject":"제목","from_":"보낸 이"}
        self._sortv.set(m.get(col,"날짜"))
        self._dirbtn.config(text="↓" if self._sort_rev else "↑")
        self._filter()

    def _render_tree(self):
        def key(e):
            v = e.get(self._sort_col, "")
            if self._sort_col == "date":
                if not v:
                    return datetime.datetime.min
                # 시간대 정보 제거해서 naive datetime으로 통일
                if hasattr(v, "tzinfo") and v.tzinfo is not None:
                    v = v.replace(tzinfo=None)
                return v
            return str(v).lower()

        self._filtered.sort(key=key, reverse=self._sort_rev)
        self._tree.delete(*self._tree.get_children())
        self._idx_map.clear()
        for i, e in enumerate(self._filtered):
            iid = str(i)
            dt  = e["date"].strftime("%y.%m.%d") if e["date"] else ""
            self._tree.insert("", "end", iid=iid,
                              values=(e["subject"], e["from_"], dt))
            self._idx_map[iid] = e

        total  = len(self._emails)
        shown  = len(self._filtered)
        suffix = f"  ({shown}개 표시)" if shown != total else ""
        if not self._loading:
            self._status.config(text=f"총 {total}개{suffix}")

    # ── 선택 & 상세 ────────────────────────────────────────
    def _on_select(self, _event):
        sel = self._tree.selection()
        if not sel:
            return
        e = self._idx_map.get(sel[0])
        if not e:
            return
        self._current = e
        try:
            parse_body(e)          # 지연 파싱
        except Exception:
            e["body_text"]   = f"[본문 파싱 오류]\n{traceback.format_exc()}"
            e["body_html"]   = ""
            e["attachments"] = []
        try:
            self._show_detail(e)
        except Exception:
            messagebox.showerror("표시 오류", traceback.format_exc()[:800])

    def _show_detail(self, e):
        self._hvars["subject"].set(e["subject"])
        self._hvars["from_"].set(e["from_"])
        self._hvars["to"].set(e["to"])
        self._hvars["cc"].set(e["cc"] or "")
        self._hvars["date_str"].set(e["date_str"])

        self._body.config(state="normal")
        self._body.delete("1.0","end")
        try:
            # null byte 등 tk.Text가 처리 못하는 문자 제거
            body = (e["body_text"] or "(텍스트 본문 없음)")
            body = body.replace("\x00", "").replace("\r\n", "\n").replace("\r", "\n")
            self._body.insert("end", body)
        except Exception:
            self._body.insert("end", "[본문 표시 오류]")
        self._body.config(state="disabled")

        # HTML 탭: 본문 유무에 따라 버튼 활성/비활성
        if e.get("body_html"):
            self._html_btn.config(state="normal")
            self._html_no_content.pack_forget()
        else:
            self._html_btn.config(state="disabled")
            self._html_no_content.pack(pady=4)

        self._af.pack_forget()
        for w in self._af.winfo_children():
            w.destroy()
        if e["attachments"]:
            self._af.pack(fill="x", padx=6, pady=(0,4), before=self._nb)
            for fn, ct, data in e["attachments"]:
                row = tk.Frame(self._af)
                row.pack(fill="x", pady=1)
                tk.Label(row, text=f"📎 {fn}", anchor="w",
                         font=("Malgun Gothic",9)).pack(side="left")
                tk.Button(row, text="저장", padx=8, relief="groove",
                          command=lambda f=fn, d=data: self._save_attach(f,d)
                          ).pack(side="right")

    # ── 계정 / 작성 / IMAP ────────────────────────────────
    def _show_about(self):
        win = tk.Toplevel(self)
        win.title("정보")
        win.geometry("320x200")
        win.resizable(False, False)
        win.grab_set()
        tk.Label(win, text="📧", font=("", 36)).pack(pady=(20, 4))
        tk.Label(win, text="Axiosoft EML 뷰어",
                 font=("Malgun Gothic", 13, "bold")).pack()
        tk.Label(win, text="Copyright \u00a9 2025 Axiosoft\nAll rights reserved.",
                 font=("Malgun Gothic", 9), fg="#555", justify="center").pack(pady=6)
        tk.Button(win, text="확인", command=win.destroy,
                  relief="groove", padx=20, pady=4).pack(pady=8)

    def _manage_accounts(self):
        if HAS_MAIL:
            AccountManagerDialog(self)

    def _compose_new(self):
        if not HAS_MAIL: return
        accounts = load_accounts()
        if not accounts:
            messagebox.showinfo("알림", "먼저 계정을 설정해 주세요.\n계정 메뉴 → 계정 관리")
            return
        ComposeWindow(self, accounts[0])

    def _compose_reply(self):
        if not HAS_MAIL: return
        if not self._current:
            messagebox.showinfo("알림", "답장할 이메일을 선택하세요.")
            return
        accounts = load_accounts()
        if not accounts:
            messagebox.showinfo("알림", "먼저 계정을 설정해 주세요.")
            return
        ComposeWindow(self, accounts[0], reply_to=self._current)

    def _fetch_imap(self):
        if not HAS_MAIL: return
        accounts = load_accounts()
        if not accounts:
            messagebox.showinfo("알림", "먼저 계정을 설정해 주세요.\n계정 메뉴 → 계정 관리")
            return
        ImapFetchDialog(self, accounts)

    def _clear_detail(self):
        for v in self._hvars.values():
            v.set("")
        self._body.config(state="normal")
        self._body.delete("1.0","end")
        self._body.config(state="disabled")
        self._af.pack_forget()

    # ── 첨부파일 저장 ──────────────────────────────────────
    def _save_attach(self, filename, data):
        ext  = Path(filename).suffix or ""
        path = filedialog.asksaveasfilename(
            initialfile=filename, defaultextension=ext,
            filetypes=[(f"{ext} 파일", f"*{ext}"), ("모든 파일","*.*")])
        if not path:
            return
        with open(path, "wb") as f:
            f.write(data)
        messagebox.showinfo("저장 완료", f"저장했습니다:\n{path}")

    # ── HTML 브라우저 ───────────────────────────────────────
    def _open_html(self):
        """pywebview 있으면 앱 내 창, 없으면 기본 브라우저"""
        if not self._current or not self._current.get("body_html"):
            messagebox.showinfo("알림", "HTML 본문이 없습니다.")
            return
        html = self._current["body_html"]
        # pywebview 방식
        if self._html_panel:
            try:
                subject = self._current.get("subject", "HTML 미리보기")
                self._html_panel.show(html, title=subject)
                return
            except Exception:
                pass  # 실패 시 브라우저 폴백
        # 기본 브라우저 방식 (charset 보장)
        if html and "charset" not in html[:500].lower():
            if "<head>" in html[:200].lower():
                html = html.replace("<head>", '<head><meta charset="utf-8">', 1)
            elif "<html>" in html[:200].lower():
                html = html.replace("<html>", '<html><head><meta charset="utf-8"></head>', 1)
            else:
                html = '<meta charset="utf-8">' + html
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html",
                                          mode="w", encoding="utf-8")
        tmp.write(html)
        tmp.close()
        webbrowser.open(f"file:///{tmp.name}")

    def _html_browser(self):
        """인쇄 등 다른 곳에서 호출하는 브라우저 열기"""
        self._open_html()

    # ── 인쇄 ──────────────────────────────────────────────
    def print_email(self):
        if not self._current:
            messagebox.showinfo("알림", "먼저 이메일을 선택하세요.")
            return
        e = self._current
        att = ""
        if e.get("attachments"):
            items = "".join(f"<li>{self._esc(fn)}</li>" for fn,_,__ in e["attachments"])
            att = f"<h3>첨부파일</h3><ul>{items}</ul>"
        html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<style>
  body{{font-family:'Malgun Gothic',sans-serif;margin:36px;font-size:13px}}
  table{{border-collapse:collapse;width:100%;margin-bottom:16px}}
  td{{padding:5px 8px;border-bottom:1px solid #eee}}
  td:first-child{{color:#666;width:72px;white-space:nowrap}}
  h2{{font-size:16px;margin-bottom:10px}}
  pre{{white-space:pre-wrap;font-family:inherit;line-height:1.7}}
</style></head><body>
<h2>{self._esc(e['subject'])}</h2>
<table>
  <tr><td>보낸 이</td><td>{self._esc(e['from_'])}</td></tr>
  <tr><td>받는 이</td><td>{self._esc(e['to'])}</td></tr>
  <tr><td>참조</td><td>{self._esc(e['cc'])}</td></tr>
  <tr><td>날짜</td><td>{self._esc(e['date_str'])}</td></tr>
</table>{att}
<pre>{self._esc(e.get('body_text') or '')}</pre>
</body></html>"""
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".html",
                                          mode="w", encoding="utf-8")
        tmp.write(html)
        tmp.close()
        webbrowser.open(f"file:///{tmp.name}")

    @staticmethod
    def _esc(s):
        return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")




class ImapFetchDialog(tk.Toplevel):
    """IMAP 받아오기 다이얼로그"""
    def __init__(self, parent, accounts: list):
        super().__init__(parent)
        self.title("메일 받아오기 (IMAP)")
        self.geometry("460x300")
        self.resizable(False, False)
        self.grab_set()
        self._parent = parent
        self._accounts = accounts
        self._build()

    def _build(self):
        pad = dict(padx=14, pady=6)
        tk.Label(self, text="계정 선택:", anchor="w").grid(row=0, column=0, sticky="w", **pad)
        self._acc_var = tk.StringVar()
        names = [f"{a['name']} <{a['email']}>" for a in self._accounts]
        self._acc_var.set(names[0])
        ttk.Combobox(self, textvariable=self._acc_var, values=names,
                     width=36, state="readonly").grid(row=0, column=1, sticky="w", **pad)

        tk.Label(self, text="저장 폴더:", anchor="w").grid(row=1, column=0, sticky="w", **pad)
        self._dir_var = tk.StringVar(value=str(
            __import__('pathlib').Path.home() / "이메일백업"))
        dir_f = tk.Frame(self)
        dir_f.grid(row=1, column=1, sticky="w", **pad)
        tk.Entry(dir_f, textvariable=self._dir_var, width=28).pack(side="left")
        tk.Button(dir_f, text="…", command=self._browse, relief="groove", padx=4).pack(side="left", padx=2)

        tk.Label(self, text="받을 메일 수:", anchor="w").grid(row=2, column=0, sticky="w", **pad)
        self._limit_var = tk.IntVar(value=200)
        ttk.Combobox(self, textvariable=self._limit_var,
                     values=[50,100,200,500,1000], width=8,
                     state="readonly").grid(row=2, column=1, sticky="w", **pad)

        tk.Label(self, text="받은편지함:", anchor="w").grid(row=3, column=0, sticky="w", **pad)
        self._folder_var = tk.StringVar(value="INBOX")
        tk.Entry(self, textvariable=self._folder_var, width=20).grid(row=3, column=1, sticky="w", **pad)

        # 진행 상황
        self._prog_lbl = tk.Label(self, text="", fg="#555")
        self._prog_lbl.grid(row=4, column=0, columnspan=2, pady=4)
        self._pb = ttk.Progressbar(self, length=400, mode="determinate")
        self._pb.grid(row=5, column=0, columnspan=2, padx=14)

        btn_f = tk.Frame(self)
        btn_f.grid(row=6, column=0, columnspan=2, pady=10)
        self._fetch_btn = tk.Button(btn_f, text="받아오기 시작", relief="groove",
                                     padx=14, command=self._start)
        self._fetch_btn.pack(side="left", padx=6)
        tk.Button(btn_f, text="닫기", relief="groove", padx=10,
                  command=self.destroy).pack(side="left")

    def _browse(self):
        d = __import__('tkinter.filedialog', fromlist=['askdirectory']).askdirectory()
        if d:
            self._dir_var.set(d)

    def _start(self):
        idx = [f"{a['name']} <{a['email']}>" for a in self._accounts].index(self._acc_var.get())
        account = self._accounts[idx]
        save_dir = self._dir_var.get()
        limit = self._limit_var.get()
        folder = self._folder_var.get() or "INBOX"

        self._fetch_btn.config(state="disabled")
        self._pb["value"] = 0

        def on_progress(done, total, saved, skipped):
            self.after(0, lambda: (
                self._pb.config(maximum=total, value=done),
                self._prog_lbl.config(text=f"{done}/{total}  저장 {saved}개  스킵 {skipped}개")
            ))

        def on_done(saved, skipped, path):
            self.after(0, lambda: (
                self._prog_lbl.config(text=f"완료! 저장 {saved}개 / 스킵 {skipped}개"),
                self._fetch_btn.config(state="normal"),
                __import__('tkinter.messagebox', fromlist=['askokcancel']).showinfo(
                    "받아오기 완료",
                    f"저장: {saved}개\n스킵(중복): {skipped}개\n폴더: {path}\n\n목록에 추가하려면 '폴더 열기'로 해당 폴더를 여세요.",
                    parent=self)
            ))

        def on_error(msg):
            self.after(0, lambda: (
                self._fetch_btn.config(state="normal"),
                self._prog_lbl.config(text="오류 발생"),
                __import__('tkinter.messagebox', fromlist=['showerror']).showerror("오류", msg, parent=self)
            ))

        fetch_imap(account, save_dir, on_progress, on_done, on_error, folder, limit)


if __name__ == "__main__":
    app = App()
    app.mainloop()
